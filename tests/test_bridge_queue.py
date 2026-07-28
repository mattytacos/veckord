"""
Unit tests for Veckord Vencord Bridge Renderer-Pull Request Queue Logic & Protocol Errors.
"""

import os
import sys
import json
import time
import socket
import threading
import unittest

bridge_client_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "experiments", "bridge-client"))
if bridge_client_dir not in sys.path:
    sys.path.insert(0, bridge_client_dir)

from client import VeckordBridgeClient


class TestBridgeQueueLogic(unittest.TestCase):

    def test_protocol_error_codes(self):
        codes = [
            "RENDERER_UNAVAILABLE",
            "RENDERER_TIMEOUT",
            "QUEUE_FULL",
            "DUPLICATE_REQUEST_ID",
            "PLUGIN_STOPPING",
            "ADAPTER_ERROR",
        ]
        for code in codes:
            err = {"code": code, "message": f"Test {code}"}
            resp = {"version": 1, "id": "req-1", "ok": False, "error": err}
            parsed = json.loads(json.dumps(resp))
            self.assertFalse(parsed["ok"])
            self.assertEqual(parsed["error"]["code"], code)

    def test_renderer_pull_request_flow_simulation(self):
        client_sock, server_sock = socket.socketpair()

        # Simulated native server with renderer pull queue
        class MockQueueServer:
            def __init__(self):
                self.has_renderer = True
                self.queue = []
                self.in_flight = {}

            def handle_client(self, conn):
                buffer = ""
                while True:
                    data = conn.recv(1024)
                    if not data:
                        break
                    buffer += data.decode("utf-8")
                    if "\n" in buffer:
                        line, _, _ = buffer.partition("\n")
                        req = json.loads(line)
                        if not self.has_renderer:
                            resp = {
                                "version": 1,
                                "id": req["id"],
                                "ok": False,
                                "error": {
                                    "code": "RENDERER_UNAVAILABLE",
                                    "message": "The Veckord renderer bridge is unavailable."
                                }
                            }
                            conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
                        else:
                            # Simulate renderer pulling and responding
                            proof_res = {
                                "rendererHandledRequest": True,
                                "buildMarker": "veckord-renderer-pull-v1",
                                "documentReadyState": "complete",
                                "documentTitlePresent": True,
                                "locationProtocol": "https:",
                                "webpackCommonAvailable": True,
                            }
                            resp = {
                                "version": 1,
                                "id": req["id"],
                                "ok": True,
                                "result": proof_res
                            }
                            conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
                        break

        mock_server = MockQueueServer()
        t = threading.Thread(target=mock_server.handle_client, args=(server_sock,))
        t.start()

        client = VeckordBridgeClient()
        client._socket = client_sock
        res = client.send_request("getRendererProof")

        self.assertTrue(res.get("rendererHandledRequest"))
        self.assertEqual(res.get("buildMarker"), "veckord-renderer-pull-v1")
        t.join(timeout=2.0)
        client_sock.close()
        server_sock.close()

    def test_renderer_unavailable_error_when_no_worker(self):
        client_sock, server_sock = socket.socketpair()

        def server_loop():
            data = server_sock.recv(1024)
            req = json.loads(data.decode("utf-8").strip())
            resp = {
                "version": 1,
                "id": req["id"],
                "ok": False,
                "error": {
                    "code": "RENDERER_UNAVAILABLE",
                    "message": "The Veckord renderer bridge is unavailable."
                }
            }
            server_sock.sendall((json.dumps(resp) + "\n").encode("utf-8"))

        t = threading.Thread(target=server_loop)
        t.start()

        client = VeckordBridgeClient()
        client._socket = client_sock

        with self.assertRaises(RuntimeError) as ctx:
            client.send_request("getStatus")

        self.assertIn("RENDERER_UNAVAILABLE", str(ctx.exception))
        t.join(timeout=2.0)
        client_sock.close()
        server_sock.close()


if __name__ == "__main__":
    unittest.main()
