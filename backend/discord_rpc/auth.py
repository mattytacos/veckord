"""
Discord RPC Authorization and Authentication Module.

Implements RPC token acquisition via HTTP, AUTHORIZE command with rpc_token (omitting redirect_uri),
OAuth2 code exchange over HTTP, and AUTHENTICATE command.
Ensures credential redaction from logs and exceptions.
"""

import os
import json
import urllib.parse
import urllib.request
import urllib.error
import logging
from typing import Any, Dict, List, Optional

from backend.discord_rpc.client import DiscordRPCClient
from backend.discord_rpc.connection import (
    ConnectionError,
    RPCCommandError,
    UserDeniedError,
)

logger = logging.getLogger(__name__)


class AuthError(ConnectionError):
    """Base exception for authorization and authentication errors."""
    pass


class MissingClientSecretError(AuthError):
    """Raised when OAuth token exchange is attempted without VECKORD_DISCORD_CLIENT_SECRET."""
    pass


class RPCTokenRequestFailedError(AuthError):
    """Raised when HTTP POST request to /oauth2/token/rpc fails."""
    def __init__(self, status_code: int, message: str):
        super().__init__(f"RPC token request failed [{status_code}]: {message}")
        self.status_code = status_code
        self.message = message


class RPCTesterNotApprovedError(RPCTokenRequestFailedError):
    """Raised when Discord account is not listed as an approved tester for the application."""
    def __init__(self, status_code: int, message: str = "Discord account is not listed as an approved tester for this application."):
        super().__init__(status_code=status_code, message=message)


class MalformedRPCTokenError(AuthError):
    """Raised when HTTP response from /oauth2/token/rpc does not contain valid rpc_token."""
    pass


class ExpiredRPCTokenError(AuthError):
    """Raised when the RPC token has expired or already been consumed."""
    pass


class TokenExchangeFailedError(AuthError):
    """Raised when HTTP OAuth2 token exchange request fails."""
    def __init__(self, status_code: int, message: str):
        super().__init__(f"OAuth token exchange failed [{status_code}]: {message}")
        self.status_code = status_code
        self.message = message


class InvalidTokenError(AuthError):
    """Raised when AUTHENTICATE command fails or token is expired/invalid."""
    pass


def sanitize_token(token: Optional[str]) -> str:
    """Return a redacted representation of a secret token for safe logging."""
    if not token:
        return "<NONE>"
    if len(token) <= 8:
        return "***"
    return f"{token[:3]}...{token[-3:]}"


class AuthManager:
    """
    Manages Discord RPC Token acquisition, AUTHORIZE command, HTTP Token Exchange, and RPC Authentication.
    """

    DEFAULT_SCOPES = ["rpc", "identify"]

    def __init__(self, client: DiscordRPCClient):
        self.client = client
        self._consumed_tokens = set()

    def request_rpc_token(self, client_id: Optional[str] = None, client_secret: Optional[str] = None) -> str:
        """
        Request a one-time RPC token via HTTP POST to https://discord.com/api/oauth2/token/rpc.
        
        Credentials are sent form-encoded ONLY in the HTTP request body.
        The returned rpc_token remains in memory only and is sanitized in logs.
        """
        cid = client_id or self.client.client_id or os.environ.get("VECKORD_DISCORD_CLIENT_ID") or os.environ.get("DECKORD_DISCORD_CLIENT_ID")
        secret = client_secret or os.environ.get("VECKORD_DISCORD_CLIENT_SECRET") or os.environ.get("DECKORD_DISCORD_CLIENT_SECRET")

        if not cid:
            raise AuthError("No Discord Client ID configured.")
        if not secret:
            raise MissingClientSecretError("RPC token request requires VECKORD_DISCORD_CLIENT_SECRET environment variable.")

        url = "https://discord.com/api/v10/oauth2/token/rpc"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "VeckordRPC/1.0",
        }
        data_params = {
            "client_id": str(cid),
            "client_secret": str(secret),
        }
        encoded_data = urllib.parse.urlencode(data_params).encode("utf-8")

        req = urllib.request.Request(url, data=encoded_data, headers=headers, method="POST")

        logger.info("Requesting one-time RPC token from https://discord.com/api/oauth2/token/rpc")

        try:
            with urllib.request.urlopen(req, timeout=10.0) as response:
                body = response.read().decode("utf-8")
                try:
                    payload = json.loads(body)
                except Exception as e:
                    raise MalformedRPCTokenError(f"Failed to parse JSON response from RPC token endpoint: {e}") from e

                if isinstance(payload, dict) and "rpc_token" in payload:
                    token = payload["rpc_token"]
                    logger.info(f"One-time RPC token obtained successfully ({sanitize_token(token)})")
                    return str(token)

                raise MalformedRPCTokenError(f"RPC token endpoint response missing 'rpc_token' key: {body}")

        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)
            logger.error(f"RPC token request HTTP error {e.code}: {err_body}")
            
            if e.code in (401, 403) or "tester" in err_body.lower() or "unauthorized" in err_body.lower():
                raise RPCTesterNotApprovedError(e.code, f"Discord account or application not approved for RPC: {err_body}") from e
                
            raise RPCTokenRequestFailedError(e.code, f"HTTP {e.code}: {err_body}") from e
        except Exception as e:
            if isinstance(e, AuthError):
                raise
            logger.error(f"RPC token request failed: {e}")
            raise RPCTokenRequestFailedError(500, str(e)) from e

    def authorize(
        self,
        rpc_token: Optional[str] = None,
        scopes: Optional[List[str]] = None,
    ) -> str:
        """
        Send RPC AUTHORIZE command using a one-time RPC token.
        
        CRITICAL: Local RPC AUTHORIZE command payload MUST NOT include redirect_uri.
        Payload contains only client_id, scopes, and optional rpc_token.
        """
        requested_scopes = scopes or self.DEFAULT_SCOPES
        if "messages.read" in requested_scopes:
            raise AuthError("Scope 'messages.read' is prohibited by project security rules.")

        if rpc_token:
            if rpc_token in self._consumed_tokens:
                raise ExpiredRPCTokenError("RPC token has already been consumed and cannot be reused.")
            self._consumed_tokens.add(rpc_token)

        logger.info(f"Sending AUTHORIZE command with scopes: {requested_scopes} (rpc_token: {sanitize_token(rpc_token)})")

        # Construct args with ONLY client_id, scopes, and rpc_token. NO redirect_uri.
        args: Dict[str, Any] = {
            "client_id": str(self.client.client_id),
            "scopes": requested_scopes,
        }
        if rpc_token:
            args["rpc_token"] = rpc_token

        try:
            resp = self.client.send_command("AUTHORIZE", args=args)
            data = resp.get("data", {})
            if isinstance(data, dict) and "code" in data:
                code = data["code"]
                logger.info(f"AUTHORIZE succeeded, code received ({sanitize_token(code)})")
                return code
            
            raise AuthError(f"AUTHORIZE response missing 'code' field: {resp}")

        except UserDeniedError:
            logger.warning("User denied Discord authorization prompt.")
            raise
        except RPCCommandError as e:
            if "token" in e.message.lower() or "expired" in e.message.lower() or e.code == 4006:
                raise ExpiredRPCTokenError(f"RPC token invalid or expired: {e.message}") from e
            logger.error(f"AUTHORIZE RPC command failed: {e}")
            raise

    def exchange_code(
        self,
        code: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Exchange an authorization code for an OAuth access token over HTTP.
        """
        cid = client_id or self.client.client_id or os.environ.get("VECKORD_DISCORD_CLIENT_ID") or os.environ.get("DECKORD_DISCORD_CLIENT_ID")
        secret = client_secret or os.environ.get("VECKORD_DISCORD_CLIENT_SECRET") or os.environ.get("DECKORD_DISCORD_CLIENT_SECRET")
        
        if not secret:
            raise MissingClientSecretError("OAuth token exchange requires VECKORD_DISCORD_CLIENT_SECRET environment variable.")

        url = "https://discord.com/api/v10/oauth2/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "VeckordRPC/1.0",
        }
        data_params = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": cid,
            "client_secret": secret,
        }
        encoded_data = urllib.parse.urlencode(data_params).encode("utf-8")

        req = urllib.request.Request(url, data=encoded_data, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=10.0) as response:
                body = response.read().decode("utf-8")
                token_data = json.loads(body)
                logger.info(f"OAuth code exchange successful. Access token: {sanitize_token(token_data.get('access_token'))}")
                return token_data
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="ignore") if hasattr(e, "read") else str(e)
            logger.error(f"Token exchange HTTP error {e.code}: {err_body}")
            raise TokenExchangeFailedError(e.code, f"HTTP {e.code}: {err_body}") from e
        except Exception as e:
            logger.error(f"Token exchange failed: {e}")
            raise TokenExchangeFailedError(500, str(e)) from e

    def authenticate(self, access_token: str) -> Dict[str, Any]:
        """
        Send RPC AUTHENTICATE command using the OAuth access token.
        Validates returned scopes and user information.
        """
        logger.info(f"Sending AUTHENTICATE command with token {sanitize_token(access_token)}")

        try:
            resp = self.client.send_command(
                "AUTHENTICATE",
                args={"access_token": access_token},
            )
            data = resp.get("data", {})
            if not isinstance(data, dict):
                raise InvalidTokenError(f"AUTHENTICATE response missing data payload: {resp}")

            user = data.get("user")
            scopes = data.get("scopes", [])
            expires = data.get("expires")

            # Validate mandatory scopes
            for mandatory_scope in ["rpc", "identify"]:
                if mandatory_scope not in scopes:
                    raise AuthError(f"AUTHENTICATE granted scopes missing mandatory scope '{mandatory_scope}'. Granted: {scopes}")

            logger.info(f"AUTHENTICATE successful. User: {user.get('username') if isinstance(user, dict) else 'Unknown'}, Scopes: {scopes}")
            return {
                "user": user,
                "scopes": scopes,
                "expires": expires,
                "raw_response": resp,
            }

        except RPCCommandError as e:
            if e.code in (4006, 4009) or "invalid" in e.message.lower() or "token" in e.message.lower():
                raise InvalidTokenError(f"Token authentication failed: {e.message}") from e
            raise AuthError(f"AUTHENTICATE failed: {e}") from e
