from __future__ import annotations

import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from verify_deployment import verify_target


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/healthz":
            body = b"ok\n"
            content_type = "text/plain"
        else:
            body = b"<html><body>demo</body></html>"
            content_type = "text/html"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        return


class VerifyDeploymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_successful_paths_and_health(self) -> None:
        report = verify_target(
            self.base_url,
            ["/", "/dashboard"],
            "/healthz",
            "ok",
            2,
            False,
        )
        self.assertTrue(report["ok"])
        self.assertTrue(report["health"]["body_matches"])
        self.assertEqual([200, 200], [item["status"] for item in report["paths"]])

    def test_health_body_mismatch_fails(self) -> None:
        report = verify_target(
            self.base_url,
            ["/"],
            "/healthz",
            "ready",
            2,
            False,
        )
        self.assertFalse(report["ok"])
        self.assertFalse(report["health"]["body_matches"])


if __name__ == "__main__":
    unittest.main()
