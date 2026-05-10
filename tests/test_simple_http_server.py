import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SimpleHttpServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from simple_http_server import JsonRequestHandler, create_server

        cls.server = create_server("127.0.0.1", 0, JsonRequestHandler)
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever)
        cls.thread.daemon = True
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join(timeout=2)
        cls.server.server_close()

    def _request_json(self, path="/", method="GET", body=None):
        data = None
        headers = {}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=headers,
            method=method,
        )
        with urllib.request.urlopen(request, timeout=3) as response:
            payload = response.read().decode("utf-8")
            return response.status, response.headers["Content-Type"], json.loads(payload)

    def test_get_returns_json_response(self):
        status, content_type, payload = self._request_json("/status?source=test")

        self.assertEqual(status, 200)
        self.assertEqual(content_type, "application/json")
        self.assertEqual(payload["method"], "GET")
        self.assertEqual(payload["path"], "/status")
        self.assertEqual(payload["query"], {"source": ["test"]})

    def test_post_returns_json_body(self):
        status, content_type, payload = self._request_json(
            "/echo",
            method="POST",
            body={"message": "hello"},
        )

        self.assertEqual(status, 200)
        self.assertEqual(content_type, "application/json")
        self.assertEqual(payload["method"], "POST")
        self.assertEqual(payload["path"], "/echo")
        self.assertEqual(payload["body"], {"message": "hello"})

    def test_post_invalid_json_returns_json_error(self):
        request = urllib.request.Request(
            self.base_url + "/echo",
            data=b"{invalid",
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(request, timeout=3)

        payload = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertEqual(ctx.exception.code, 400)
        self.assertEqual(ctx.exception.headers["Content-Type"], "application/json")
        self.assertEqual(payload["error"], "invalid_json")


if __name__ == "__main__":
    unittest.main()
