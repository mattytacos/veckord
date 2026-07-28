"""
CLI module for Discord Decky Voice Controller probe commands.
"""

import sys
import os
import argparse
import logging
from backend.discord_rpc.client import DiscordRPCClient
from backend.discord_rpc.auth import AuthManager, sanitize_token, AuthError
from backend.discord_rpc.connection import ConnectionError

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def cmd_handshake(args: argparse.Namespace) -> int:
    client_id = args.client_id or os.environ.get("VECKORD_DISCORD_CLIENT_ID")
    if not client_id:
        print("Error: Environment variable VECKORD_DISCORD_CLIENT_ID is missing.", file=sys.stderr)
        return 1

    client = DiscordRPCClient(client_id=client_id, socket_path=args.socket_path, timeout=args.timeout)
    
    try:
        ready_data = client.connect_and_handshake()
        print("handshake succeeded")
        print(f"selected socket path: {client.selected_socket_path}")
        print(f"final state: {client.state.value}")
        print(f"RPC version: {client.rpc_version}")
        return 0

    except ConnectionError as e:
        print(f"handshake failed: {e}", file=sys.stderr)
        return 1
    finally:
        client.close()


def cmd_authenticate(args: argparse.Namespace) -> int:
    client_id = args.client_id or os.environ.get("VECKORD_DISCORD_CLIENT_ID") or os.environ.get("DECKORD_DISCORD_CLIENT_ID")
    client_secret = args.client_secret or os.environ.get("VECKORD_DISCORD_CLIENT_SECRET") or os.environ.get("DECKORD_DISCORD_CLIENT_SECRET")

    # Verify presence of environment variables without printing their values
    missing_vars = []
    if not client_id:
        missing_vars.append("VECKORD_DISCORD_CLIENT_ID (or DECKORD_DISCORD_CLIENT_ID)")
    if not client_secret:
        missing_vars.append("VECKORD_DISCORD_CLIENT_SECRET (or DECKORD_DISCORD_CLIENT_SECRET)")

    if missing_vars:
        print(f"Error: Required environment variable(s) missing: {', '.join(missing_vars)}", file=sys.stderr)
        return 1

    client = DiscordRPCClient(client_id=client_id, socket_path=args.socket_path, timeout=args.timeout)
    auth_mgr = AuthManager(client)

    try:
        # Step 1: Handshake
        client.connect_and_handshake()
        print("1. Handshake: SUCCEEDED")

        # Step 2: Request One-Time RPC Token
        print("2. RPC Token Request: Requesting token from Discord API...")
        rpc_token = auth_mgr.request_rpc_token(client_id=client_id, client_secret=client_secret)
        print(f"   RPC Token: {sanitize_token(rpc_token)}")

        # Step 3: Authorize with RPC Token
        print("3. Authorize: Sending AUTHORIZE command with RPC token...")
        code = auth_mgr.authorize(rpc_token=rpc_token, scopes=["rpc", "identify"])
        print(f"   Authorization Code: {sanitize_token(code)}")

        # Step 4: OAuth Token Exchange
        print("4. OAuth Exchange: Exchanging code for access token...")
        token_data = auth_mgr.exchange_code(code, client_id=client_id, client_secret=client_secret)
        access_token = token_data.get("access_token")
        print(f"   Access Token: {sanitize_token(access_token)}")

        # Step 5: Authenticate Session
        print("5. Authenticate: Validating session with Discord RPC...")
        auth_session = auth_mgr.authenticate(access_token)

        user_info = auth_session.get("user", {})
        username = user_info.get("username", "Unknown") if isinstance(user_info, dict) else "Unknown"
        user_id = user_info.get("id", "Unknown") if isinstance(user_info, dict) else "Unknown"
        scopes = auth_session.get("scopes", [])

        print("\n=== AUTHENTICATION SUCCESS ===")
        print(f"Authenticated User: {username} (ID: {user_id})")
        print(f"Granted Scopes: {', '.join(scopes)}")
        print(f"Expires: {auth_session.get('expires', 'N/A')}")
        return 0

    except Exception as e:
        print(f"\nAuthentication failed: {e}", file=sys.stderr)
        return 1
    finally:
        client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Discord RPC CLI Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # handshake subcommand
    hs_parser = subparsers.add_parser("handshake", help="Perform Discord RPC handshake")
    hs_parser.add_argument("--client-id", help="Discord Application Client ID")
    hs_parser.add_argument("--socket-path", help="Explicit Unix socket path override")
    hs_parser.add_argument("--timeout", type=float, default=5.0, help="Connection timeout in seconds")

    # authenticate subcommand
    auth_parser = subparsers.add_parser("authenticate", help="Perform Discord RPC authorization and authentication")
    auth_parser.add_argument("--client-id", help="Discord Application Client ID")
    auth_parser.add_argument("--client-secret", help="Discord Application Client Secret")
    auth_parser.add_argument("--socket-path", help="Explicit Unix socket path override")
    auth_parser.add_argument("--timeout", type=float, default=15.0, help="Connection timeout in seconds")

    args = parser.parse_args()

    if args.command == "handshake":
        return cmd_handshake(args)

    if args.command == "authenticate":
        return cmd_authenticate(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
