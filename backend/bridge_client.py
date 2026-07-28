"""
Veckord Vencord Bridge Production Socket Client.

Provides host-side Unix domain socket RPC communication between the Decky Loader backend
and the Veckord Vencord bridge plugin running in Vesktop.
"""

import os
import sys
import uuid
import json
import socket
from typing import Any, Dict, Optional


def resolve_socket_path() -> str:
    """
    Resolves the active Veckord bridge Unix domain socket path.
    Prefers primary /run/user/<uid>/veckord/bridge.sock.
    Falls back to legacy /run/user/<uid>/deckord/bridge.sock if present.
    Returns primary path when neither socket exists.
    """
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
    uid = str(os.getuid()) if hasattr(os, "getuid") else "1000"

    base_dir = xdg_runtime
    if not base_dir or not os.path.exists(base_dir):
        base_dir = f"/run/user/{uid}"

    primary_sock = os.path.join(base_dir, "veckord", "bridge.sock")
    legacy_sock = os.path.join(base_dir, "deckord", "bridge.sock")

    if not os.path.exists(primary_sock) and os.path.exists(legacy_sock):
        return legacy_sock

    return primary_sock


class VeckordBridgeClient:
    """
    Client for interacting with the Veckord Vencord local bridge Unix domain socket.
    """

    def __init__(self, socket_path: Optional[str] = None, timeout: float = 5.0):
        self.socket_path = socket_path or resolve_socket_path()
        self.timeout = timeout
        self._socket: Optional[socket.socket] = None

    def connect(self) -> None:
        if not os.path.exists(self.socket_path):
            raise FileNotFoundError(f"Veckord bridge socket not found at {self.socket_path}. Ensure Vesktop is running with Veckord plugin enabled.")

        self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._socket.settimeout(self.timeout)
        self._socket.connect(self.socket_path)

    def close(self) -> None:
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    def send_request(self, method: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self._socket:
            self.connect()

        req_id = str(uuid.uuid4())
        payload = {
            "version": 1,
            "id": req_id,
            "method": method,
            "params": params or {},
        }

        line = json.dumps(payload, separators=(",", ":")) + "\n"
        self._socket.sendall(line.encode("utf-8"))

        # Read line response
        buffer = bytearray()
        while True:
            chunk = self._socket.recv(4096)
            if not chunk:
                raise ConnectionError("Bridge socket closed connection prematurely.")
            buffer.extend(chunk)
            if b"\n" in buffer:
                break

        line_bytes, _, _ = buffer.partition(b"\n")
        resp_payload = json.loads(line_bytes.decode("utf-8"))

        if not resp_payload.get("ok"):
            err = resp_payload.get("error", {})
            code = err.get("code", "UNKNOWN_ERROR")
            msg = err.get("message", "Bridge operation failed")
            raise RuntimeError(f"Bridge Error [{code}]: {msg}")

        return resp_payload.get("result", {})
