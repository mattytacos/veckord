"""
Unit tests for Veckord Local Bridge Protocol & Python Bridge Client.
"""

import os
import sys
import json
import socket
import unittest
from unittest.mock import patch, MagicMock

# Dynamically import bridge client from experiments/bridge-client/client.py
bridge_client_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "experiments", "bridge-client"))
if bridge_client_dir not in sys.path:
    sys.path.insert(0, bridge_client_dir)

from client import VeckordBridgeClient, resolve_socket_path


class TestBridgeProtocol(unittest.TestCase):

    def test_request_response_encoding(self):
        req = {
            "version": 1,
            "id": "test-req-1",
            "method": "ping",
            "params": {}
        }
        raw_json = json.dumps(req)
        parsed = json.loads(raw_json)
        self.assertEqual(parsed["version"], 1)
        self.assertEqual(parsed["id"], "test-req-1")

    def test_resolve_socket_path(self):
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": "/run/user/1000"}):
            path = resolve_socket_path()
            self.assertEqual(path, "/run/user/1000/veckord/bridge.sock")

    def test_fragmented_newline_input_handling(self):
        client_sock, server_sock = socket.socketpair()

        def server_loop():
            buffer = ""
            while True:
                data = server_sock.recv(1024)
                if not data:
                    break
                buffer += data.decode("utf-8")
                if "\n" in buffer:
                    line, _, _ = buffer.partition("\n")
                    req = json.loads(line)
                    resp = {
                        "version": 1,
                        "id": req["id"],
                        "ok": True,
                        "result": {"pong": True}
                    }
                    server_sock.sendall((json.dumps(resp) + "\n").encode("utf-8"))
                    break

        import threading
        t = threading.Thread(target=server_loop)
        t.start()

        client = VeckordBridgeClient()
        client._socket = client_sock
        res = client.send_request("ping")
        self.assertTrue(res.get("pong"))
        t.join(timeout=2.0)
        client_sock.close()
        server_sock.close()

    def test_multiple_requests_in_one_read(self):
        client_sock, server_sock = socket.socketpair()
        processed_count = 0

        def server_loop():
            nonlocal processed_count
            buffer = ""
            while True:
                data = server_sock.recv(4096)
                if not data:
                    break
                buffer += data.decode("utf-8")
                lines = buffer.split("\n")
                buffer = lines.pop()
                for line in lines:
                    if not line.strip():
                        continue
                    req = json.loads(line)
                    resp = {"version": 1, "id": req["id"], "ok": True, "result": {"echo": req["method"]}}
                    server_sock.sendall((json.dumps(resp) + "\n").encode("utf-8"))
                    processed_count += 1
                if processed_count >= 2:
                    break

        import threading
        t = threading.Thread(target=server_loop)
        t.start()

        client = VeckordBridgeClient()
        client._socket = client_sock
        
        # Send two requests sequentially
        r1 = client.send_request("ping")
        r2 = client.send_request("getStatus")

        self.assertEqual(r1["echo"], "ping")
        self.assertEqual(r2["echo"], "getStatus")
        t.join(timeout=2.0)
        client_sock.close()
        server_sock.close()

    def test_bridge_error_response_parsing(self):
        client_sock, server_sock = socket.socketpair()

        def server_loop():
            data = server_sock.recv(1024)
            req = json.loads(data.decode("utf-8").strip())
            resp = {
                "version": 1,
                "id": req["id"],
                "ok": False,
                "error": {
                    "code": "UNKNOWN_METHOD",
                    "message": "Disallowed method"
                }
            }
            server_sock.sendall((json.dumps(resp) + "\n").encode("utf-8"))

        import threading
        t = threading.Thread(target=server_loop)
        t.start()

        client = VeckordBridgeClient()
        client._socket = client_sock

        with self.assertRaises(RuntimeError) as ctx:
            client.send_request("badMethod")

        self.assertIn("UNKNOWN_METHOD", str(ctx.exception))
        self.assertIn("Disallowed method", str(ctx.exception))
        t.join(timeout=2.0)
        client_sock.close()
        server_sock.close()


if __name__ == "__main__":
    unittest.main()
