"""
Unit tests for backend.discord_rpc authorization, RPC token request, OAuth token exchange, and authentication logic.
"""

import json
import socket
import struct
import unittest
from unittest.mock import patch, MagicMock

from backend.discord_rpc.connection import (
    ConnectionState,
    ConnectionStateMachine,
    RPCCommandError,
    UserDeniedError,
    SocketClosedError,
)
from backend.discord_rpc.client import DiscordRPCClient
from backend.discord_rpc.auth import (
    AuthManager,
    AuthError,
    MissingClientSecretError,
    RPCTokenRequestFailedError,
    RPCTesterNotApprovedError,
    MalformedRPCTokenError,
    ExpiredRPCTokenError,
    TokenExchangeFailedError,
    InvalidTokenError,
    sanitize_token,
)
from backend.discord_rpc.protocol import Opcode, encode_frame


class TestAuthManager(unittest.TestCase):

    def test_sanitize_token(self):
        self.assertEqual(sanitize_token(None), "<NONE>")
        self.assertEqual(sanitize_token(""), "<NONE>")
        self.assertEqual(sanitize_token("short"), "***")
        self.assertEqual(sanitize_token("secret_access_token_12345"), "sec...345")

    @patch("urllib.request.urlopen")
    def test_request_rpc_token_success(self, mock_urlopen):
        client = DiscordRPCClient(client_id="927962292748972032")
        auth_mgr = AuthManager(client)

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({"rpc_token": "mock_rpc_token_9999"}).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        token = auth_mgr.request_rpc_token(client_id="927962292748972032", client_secret="mock_secret")
        self.assertEqual(token, "mock_rpc_token_9999")

        # Verify endpoint and body payload
        req_arg = mock_urlopen.call_args[0][0]
        self.assertEqual(req_arg.full_url, "https://discord.com/api/v10/oauth2/token/rpc")
        self.assertEqual(req_arg.headers["Content-type"], "application/x-www-form-urlencoded")
        body_str = req_arg.data.decode("utf-8")
        self.assertIn("client_id=927962292748972032", body_str)
        self.assertIn("client_secret=mock_secret", body_str)

    @patch("urllib.request.urlopen")
    def test_request_rpc_token_tester_not_approved(self, mock_urlopen):
        client = DiscordRPCClient(client_id="927962292748972032")
        auth_mgr = AuthManager(client)

        import urllib.error
        err = urllib.error.HTTPError(
            url="https://discord.com/api/v10/oauth2/token/rpc",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=MagicMock(read=MagicMock(return_value=b'{"error": "unauthorized_client", "error_description": "Not listed as RPC tester"}'))
        )
        mock_urlopen.side_effect = err

        with self.assertRaises(RPCTesterNotApprovedError) as ctx:
            auth_mgr.request_rpc_token(client_id="927962292748972032", client_secret="mock_secret")
        self.assertEqual(ctx.exception.status_code, 403)

    @patch("urllib.request.urlopen")
    def test_request_rpc_token_malformed_response(self, mock_urlopen):
        client = DiscordRPCClient(client_id="927962292748972032")
        auth_mgr = AuthManager(client)

        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"other_key": "no_rpc_token"}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        with self.assertRaises(MalformedRPCTokenError):
            auth_mgr.request_rpc_token(client_id="927962292748972032", client_secret="mock_secret")

    def test_authorize_payload_contains_rpc_token_and_omits_redirect_uri(self):
        client = DiscordRPCClient(client_id="927962292748972032")
        client.state_machine.transition_to(ConnectionState.CONNECTING)
        client.state_machine.transition_to(ConnectionState.HANDSHAKING)
        client.state_machine.transition_to(ConnectionState.READY)

        captured_args = {}

        def mock_send_cmd(cmd, args=None, evt=None, timeout=None):
            nonlocal captured_args
            captured_args = args
            return {"cmd": "AUTHORIZE", "data": {"code": "mock_auth_code_123"}}

        client.send_command = mock_send_cmd
        auth_mgr = AuthManager(client)
        code = auth_mgr.authorize(rpc_token="mock_rpc_token_777", scopes=["rpc", "identify"])

        self.assertEqual(code, "mock_auth_code_123")
        self.assertIn("client_id", captured_args)
        self.assertIn("scopes", captured_args)
        self.assertIn("rpc_token", captured_args)
        self.assertEqual(captured_args["rpc_token"], "mock_rpc_token_777")
        # CRITICAL ASSERTION: redirect_uri MUST NOT be present in RPC AUTHORIZE payload
        self.assertNotIn("redirect_uri", captured_args)

    def test_rpc_token_not_reused(self):
        client = DiscordRPCClient(client_id="927962292748972032")
        client.state_machine.transition_to(ConnectionState.CONNECTING)
        client.state_machine.transition_to(ConnectionState.HANDSHAKING)
        client.state_machine.transition_to(ConnectionState.READY)

        client.send_command = MagicMock(return_value={"cmd": "AUTHORIZE", "data": {"code": "code1"}})
        auth_mgr = AuthManager(client)

        token = "single_use_token_123"
        auth_mgr.authorize(rpc_token=token)

        # Attempting to reuse the token raises ExpiredRPCTokenError
        with self.assertRaises(ExpiredRPCTokenError):
            auth_mgr.authorize(rpc_token=token)

    @patch("urllib.request.urlopen")
    def test_complete_mocked_authorization_and_authentication_flow(self, mock_urlopen):
        client = DiscordRPCClient(client_id="927962292748972032")
        client.state_machine.transition_to(ConnectionState.CONNECTING)
        client.state_machine.transition_to(ConnectionState.HANDSHAKING)
        client.state_machine.transition_to(ConnectionState.READY)

        auth_mgr = AuthManager(client)

        # 1. Mock HTTP responses for RPC token request & OAuth exchange
        rpc_token_resp = MagicMock()
        rpc_token_resp.read.return_value = json.dumps({"rpc_token": "rpc_tok_abc"}).encode("utf-8")
        rpc_token_resp.__enter__.return_value = rpc_token_resp

        oauth_resp = MagicMock()
        oauth_resp.read.return_value = json.dumps({
            "access_token": "access_tok_xyz",
            "token_type": "Bearer",
            "expires_in": 604800,
            "scope": "rpc identify"
        }).encode("utf-8")
        oauth_resp.__enter__.return_value = oauth_resp

        mock_urlopen.side_effect = [rpc_token_resp, oauth_resp]

        # 2. Mock RPC send_command responses for AUTHORIZE and AUTHENTICATE
        def mock_rpc_cmd(cmd, args=None, evt=None, timeout=None):
            if cmd == "AUTHORIZE":
                return {"cmd": "AUTHORIZE", "data": {"code": "auth_code_555"}}
            if cmd == "AUTHENTICATE":
                return {
                    "cmd": "AUTHENTICATE",
                    "data": {
                        "user": {"id": "999", "username": "mock_decky_user"},
                        "scopes": ["rpc", "identify"],
                        "expires": "2026-12-31T23:59:59Z"
                    }
                }
            return {}

        client.send_command = mock_rpc_cmd

        # Execute flow
        rpc_tok = auth_mgr.request_rpc_token(client_secret="secret_123")
        self.assertEqual(rpc_tok, "rpc_tok_abc")

        code = auth_mgr.authorize(rpc_token=rpc_tok, scopes=["rpc", "identify"])
        self.assertEqual(code, "auth_code_555")

        token_data = auth_mgr.exchange_code(code, client_secret="secret_123")
        self.assertEqual(token_data["access_token"], "access_tok_xyz")

        auth_session = auth_mgr.authenticate(token_data["access_token"])
        self.assertEqual(auth_session["user"]["username"], "mock_decky_user")
        self.assertIn("rpc", auth_session["scopes"])

    def test_nonce_generation_unique(self):
        client = DiscordRPCClient(client_id="927962292748972032")
        client_sock, server_sock = socket.socketpair()
        client._socket = client_sock
        client.state_machine.transition_to(ConnectionState.CONNECTING)
        client.state_machine.transition_to(ConnectionState.HANDSHAKING)
        client.state_machine.transition_to(ConnectionState.READY)

        nonces = set()
        for _ in range(5):
            def fake_send(opcode, payload):
                client._last_nonce = payload["nonce"]
                nonces.add(payload["nonce"])
                reply = encode_frame(Opcode.FRAME, {"cmd": "AUTHORIZE", "nonce": payload["nonce"], "data": {"code": "test_code_123"}})
                server_sock.sendall(reply)

            client.send_frame = fake_send
            resp = client.send_command("AUTHORIZE", args={"scopes": ["rpc"]})
            self.assertEqual(resp["data"]["code"], "test_code_123")

        self.assertEqual(len(nonces), 5)

        client.close()
        server_sock.close()

    def test_matching_responses_by_nonce(self):
        client_sock, server_sock = socket.socketpair()
        client = DiscordRPCClient(client_id="927962292748972032", timeout=1.0)
        client._socket = client_sock
        client.state_machine.transition_to(ConnectionState.CONNECTING)
        client.state_machine.transition_to(ConnectionState.HANDSHAKING)
        client.state_machine.transition_to(ConnectionState.READY)

        def fake_send(opcode, payload):
            nonce = payload["nonce"]
            reply = encode_frame(Opcode.FRAME, {"cmd": "AUTHORIZE", "nonce": nonce, "data": {"code": "abc_code"}})
            server_sock.sendall(reply)

        client.send_frame = fake_send

        resp = client.send_command("AUTHORIZE")
        self.assertEqual(resp["data"]["code"], "abc_code")

        client.close()
        server_sock.close()

    def test_user_cancellation(self):
        client = DiscordRPCClient(client_id="927962292748972032")
        client.state_machine.transition_to(ConnectionState.CONNECTING)
        client.state_machine.transition_to(ConnectionState.HANDSHAKING)
        client.state_machine.transition_to(ConnectionState.READY)

        with patch.object(client, "send_command") as mock_cmd:
            mock_cmd.side_effect = UserDeniedError("User denied authorization prompt")
            auth_mgr = AuthManager(client)
            with self.assertRaises(UserDeniedError):
                auth_mgr.authorize()

    def test_missing_client_secret(self):
        client = DiscordRPCClient(client_id="927962292748972032")
        auth_mgr = AuthManager(client)

        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(MissingClientSecretError):
                auth_mgr.request_rpc_token()

    def test_prohibit_messages_read_scope(self):
        client = DiscordRPCClient(client_id="927962292748972032")
        auth_mgr = AuthManager(client)
        with self.assertRaises(AuthError):
            auth_mgr.authorize(scopes=["rpc", "identify", "messages.read"])


if __name__ == "__main__":
    unittest.main()
