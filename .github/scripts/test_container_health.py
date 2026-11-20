"""Real local HTTP fixtures exercise the shipped curl health probe."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import os
import subprocess
import threading
import socket
import time
import unittest

PROBE = Path(__file__).resolve().parents[2] / 'distribution/docker/healthcheck.sh'


class HealthTests(unittest.TestCase):
    def test_exact_200_only(self):
        self.assertTrue(PROBE.exists(), 'container health must reject redirects and unexpected success statuses')
        for status in (200, 204, 302, 401, 500):
            paths = []
            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    paths.append(self.path)
                    self.send_response(status)
                    self.end_headers()

                def log_message(self, *args):
                    pass

            with HTTPServer(('127.0.0.1', 0), Handler) as server:
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    env = dict(os.environ, http_proxy='http://127.0.0.1:1',
                               HTTP_PROXY='http://127.0.0.1:1', all_proxy='http://127.0.0.1:1',
                               ALL_PROXY='http://127.0.0.1:1', NO_PROXY='', no_proxy='')
                    result = subprocess.run(['sh', str(PROBE), str(server.server_port)],
                                            capture_output=True, env=env, timeout=5)
                    self.assertEqual(result.returncode == 0, status == 200, status)
                    self.assertEqual(result.stdout, b'')
                    self.assertEqual(result.stderr, b'')
                    self.assertEqual(paths, ['/ping'])
                finally:
                    server.shutdown()
                    worker.join()

    def test_connection_refusal_is_quiet_failure(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
            result = subprocess.run(['sh', str(PROBE), str(port)], capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout + result.stderr, b'')

    def test_unresponsive_server_is_bounded(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen()
            start = time.monotonic()
            result = subprocess.run(['sh', str(PROBE), str(listener.getsockname()[1])],
                                    capture_output=True, timeout=5)
            self.assertLess(time.monotonic() - start, 4.5)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout + result.stderr, b'')


if __name__ == '__main__':
    unittest.main()
