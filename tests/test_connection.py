"""
Unit tests for backend.discord_rpc connection state machine and client logic.
"""

import json
import socket
import struct
import unittest
from unittest.mock import patch, MagicMock

from backend.discord_rpc.connection import (
    ConnectionState,
    ConnectionStateMachine,
    InvalidStateTransitionError,
    MissingClientIdError,
    SocketNotFoundError,
    HandshakeFailedError,
    TimeoutError,
    SocketClosedError,
    ConnectionError,
)
from backend.discord_rpc.client import DiscordRPCClient
from backend.discord_rpc.protocol import Opcode, encode_frame, HEADER_STRUCT


class TestConnectionStateMachine(unittest.TestCase):

    def test_valid_transitions(self):
        sm = ConnectionStateMachine()
        self.assertEqual(sm.state, ConnectionState.DISCONNECTED)

        sm.transition_to(ConnectionState.DISCOVERING)
        self.assertEqual(sm.state, ConnectionState.DISCOVERING)

        sm.transition_to(ConnectionState.CONNECTING)
        self.assertEqual(sm.state, ConnectionState.CONNECTING)

        sm.transition_to(ConnectionState.HANDSHAKING)
        self.assertEqual(sm.state, ConnectionState.HANDSHAKING)

        sm.transition_to(ConnectionState.READY)
        self.assertEqual(sm.state, ConnectionState.READY)

        sm.transition_to(ConnectionState.CLOSING)
        self.assertEqual(sm.state, ConnectionState.CLOSING)

        sm.transition_to(ConnectionState.DISCONNECTED)
        self.assertEqual(sm.state, ConnectionState.DISCONNECTED)

    def test_invalid_transitions(self):
        sm = ConnectionStateMachine()
        with self.assertRaises(InvalidStateTransitionError):
            sm.transition_to(ConnectionState.READY)

        with self.assertRaises(InvalidStateTransitionError):
            sm.transition_to(ConnectionState.HANDSHAKING)

    def test_reset(self):
        sm = ConnectionStateMachine()
        sm.transition_to(ConnectionState.DISCOVERING)
        sm.reset()
        self.assertEqual(sm.state, ConnectionState.DISCONNECTED)


class TestDiscordRPCClient(unittest.TestCase):

    def test_missing_client_id(self):
        client = DiscordRPCClient(client_id=None)
        with patch.dict("os.environ", {}, clear=True):
            client.client_id = None
            with self.assertRaises(MissingClientIdError):
                client.connect_and_handshake()

    @patch("backend.discord_rpc.client.get_active_ipc_socket")
    def test_no_socket_found(self, mock_discovery):
        mock_discovery.return_value = None
        client = DiscordRPCClient(client_id="123456789")
        with self.assertRaises(SocketNotFoundError):
            client.connect_and_handshake()

    def test_successful_ready_response(self):
        client_sock, server_sock = socket.socketpair()
        client = DiscordRPCClient(client_id="927962292748972032", timeout=1.0)
        client._socket = client_sock
        client.state_machine.transition_to(ConnectionState.CONNECTING)
        client.state_machine.transition_to(ConnectionState.HANDSHAKING)

        # Server sends back READY dispatch frame
        ready_payload = {
            "cmd": "DISPATCH",
            "evt": "READY",
            "data": {
                "v": 1,
                "config": {"api_endpoint": "//discord.com/api"},
                "user": {"id": "100", "username": "test_user"}
            }
        }
        server_sock.sendall(encode_frame(Opcode.FRAME, ready_payload))

        # Client reads READY frame
        res = client._wait_for_ready_event()
        self.assertEqual(res["evt"], "READY")
        self.assertEqual(res["data"]["user"]["username"], "test_user")

        client.close()
        server_sock.close()

    def test_fragmented_ready_frame(self):
        client_sock, server_sock = socket.socketpair()
        client = DiscordRPCClient(client_id="927962292748972032", timeout=1.0)
        client._socket = client_sock
        client.state_machine.transition_to(ConnectionState.CONNECTING)
        client.state_machine.transition_to(ConnectionState.HANDSHAKING)

        ready_payload = {"cmd": "DISPATCH", "evt": "READY", "data": {"v": 1}}
        frame_bytes = encode_frame(Opcode.FRAME, ready_payload)

        # Send frame in 2 fragments
        server_sock.sendall(frame_bytes[:10])
        server_sock.sendall(frame_bytes[10:])

        res = client._wait_for_ready_event()
        self.assertEqual(res["evt"], "READY")

        client.close()
        server_sock.close()

    def test_ping_pong_handling(self):
        client_sock, server_sock = socket.socketpair()
        client = DiscordRPCClient(client_id="927962292748972032", timeout=1.0)
        client._socket = client_sock
        client.state_machine.transition_to(ConnectionState.CONNECTING)
        client.state_machine.transition_to(ConnectionState.HANDSHAKING)

        # Server sends PING before client reads
        server_sock.sendall(encode_frame(Opcode.PING, {"nonce": "xyz"}))

        # Client reads frame
        frame = client.read_frame()
        self.assertEqual(frame.opcode, Opcode.PING)

        # Server receives auto PONG
        pong_data = server_sock.recv(1024)
        opcode_raw, length = struct.unpack("<II", pong_data[:8])
        self.assertEqual(opcode_raw, int(Opcode.PONG))
        pong_payload = json.loads(pong_data[8:8+length].decode("utf-8"))
        self.assertEqual(pong_payload, {"nonce": "xyz"})

        client.close()
        server_sock.close()

    def test_close_before_ready(self):
        client_sock, server_sock = socket.socketpair()
        client = DiscordRPCClient(client_id="927962292748972032", timeout=1.0)
        client._socket = client_sock
        client.state_machine.transition_to(ConnectionState.CONNECTING)
        client.state_machine.transition_to(ConnectionState.HANDSHAKING)

        # Server sends CLOSE frame
        server_sock.sendall(encode_frame(Opcode.CLOSE, {"code": 4000, "message": "Invalid client_id"}))

        with self.assertRaises(SocketClosedError):
            client._wait_for_ready_event()

        client.close()
        server_sock.close()

    def test_eof_before_ready(self):
        client_sock, server_sock = socket.socketpair()
        client = DiscordRPCClient(client_id="927962292748972032", timeout=1.0)
        client._socket = client_sock
        client.state_machine.transition_to(ConnectionState.CONNECTING)
        client.state_machine.transition_to(ConnectionState.HANDSHAKING)

        # Server closes socket immediately
        server_sock.close()

        with self.assertRaises(SocketClosedError):
            client._wait_for_ready_event()

        client.close()

    def test_timeout(self):
        client_sock, server_sock = socket.socketpair()
        client = DiscordRPCClient(client_id="927962292748972032", timeout=0.1)
        client._socket = client_sock
        client.state_machine.transition_to(ConnectionState.CONNECTING)

        with self.assertRaises(TimeoutError):
            client.read_frame(timeout=0.1)

        client.close()
        server_sock.close()

    def test_malformed_ready_response(self):
        client_sock, server_sock = socket.socketpair()
        client = DiscordRPCClient(client_id="927962292748972032", timeout=1.0)
        client._socket = client_sock
        client.state_machine.transition_to(ConnectionState.CONNECTING)
        client.state_machine.transition_to(ConnectionState.HANDSHAKING)

        # Send invalid non-READY payload frame
        server_sock.sendall(encode_frame(Opcode.FRAME, {"cmd": "UNKNOWN", "data": {}}))

        with self.assertRaises(HandshakeFailedError):
            client._wait_for_ready_event()

        client.close()
        server_sock.close()

    def test_socket_cleanup_after_failure(self):
        client = DiscordRPCClient(client_id="927962292748972032")
        with patch("backend.discord_rpc.client.get_active_ipc_socket", return_value=None):
            try:
                client.connect_and_handshake()
            except ConnectionError:
                pass
            self.assertEqual(client.state, ConnectionState.FAILED)
            self.assertIsNone(client._socket)

    def test_repeated_close_calls(self):
        client = DiscordRPCClient(client_id="927962292748972032")
        client.close()
        self.assertEqual(client.state, ConnectionState.DISCONNECTED)
        client.close()
        client.close()
        self.assertEqual(client.state, ConnectionState.DISCONNECTED)


if __name__ == "__main__":
    unittest.main()
