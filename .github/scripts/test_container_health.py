"""Real local HTTP fixtures exercise the shipped curl health probe."""
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import os
import subprocess
import threading
import unittest

PROBE = Path(__file__).resolve().parents[2] / 'distribution/docker/healthcheck.sh'


class HealthTests(unittest.TestCase):
    def test_exact_200_only(self):
        self.assertTrue(PROBE.exists(), 'container health must reject redirects and unexpected success statuses')
        for status in (200, 204, 302, 401, 500):
            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(status)
                    self.end_headers()

                def log_message(self, *args):
                    pass

            with HTTPServer(('127.0.0.1', 0), Handler) as server:
                worker = threading.Thread(target=server.serve_forever, daemon=True)
                worker.start()
                try:
                    env = dict(os.environ, http_proxy='http://127.0.0.1:1',
                               ALL_PROXY='http://127.0.0.1:1', NO_PROXY='')
                    result = subprocess.run(['sh', str(PROBE), str(server.server_port)],
                                            capture_output=True, env=env, timeout=5)
                    self.assertEqual(result.returncode == 0, status == 200, status)
                    self.assertEqual(result.stdout, b'')
                    self.assertEqual(result.stderr, b'')
                finally:
                    server.shutdown()
                    worker.join()


if __name__ == '__main__':
    unittest.main()
