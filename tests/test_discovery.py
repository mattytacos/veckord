"""
Unit tests for backend.discord_rpc.discovery.
"""

import os
import socket
import unittest
import tempfile
from backend.discord_rpc.discovery import (
    get_dynamic_candidate_paths,
    inspect_and_probe_socket,
    find_all_ipc_sockets,
    get_active_ipc_socket,
    SocketMetadata,
)


class TestDiscovery(unittest.TestCase):
    def test_candidate_socket_paths_non_empty(self):
        candidates = get_dynamic_candidate_paths()
        self.assertGreater(len(candidates), 0)
        paths = [p for p, _ in candidates]
        self.assertIn("/tmp/discord-ipc-0", paths)

    def test_inspect_nonexistent_path(self):
        res = inspect_and_probe_socket("/path/that/does/not/exist/at/all", "test")
        self.assertFalse(res.exists)
        self.assertFalse(res.is_socket)
        self.assertFalse(res.can_connect)
        self.assertEqual(res.client_type, "test")

    def test_inspect_regular_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=True) as tmp:
            tmp.write("hello")
            tmp.flush()
            res = inspect_and_probe_socket(tmp.name, "test")
            self.assertTrue(res.exists)
            self.assertFalse(res.is_socket)
            self.assertFalse(res.can_connect)

    def test_inspect_real_unix_socket(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            sock_path = os.path.join(tmpdir, "test-ipc-0")
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(sock_path)
            server.listen(1)

            try:
                res = inspect_and_probe_socket(sock_path, "test")
                self.assertTrue(res.exists)
                self.assertTrue(res.is_socket)
                self.assertTrue(res.can_connect)
                self.assertIn("SOCKET", str(res))
                self.assertIn("CONNECTED", str(res))
            finally:
                server.close()


if __name__ == "__main__":
    unittest.main()
