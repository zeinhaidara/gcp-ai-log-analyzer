import io
import json
import tempfile
import unittest
from pathlib import Path
from app import create_app


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = str(Path(self.temp.name) / "logs.db")
        self.app = create_app(self.database)

    def tearDown(self):
        self.temp.cleanup()

    def request(self, path, method="GET", payload=None, raw=None, length=None):
        body = raw if raw is not None else json.dumps(payload).encode() if payload is not None else b""
        statuses = []
        result = self.app({"PATH_INFO": path, "REQUEST_METHOD": method, "CONTENT_LENGTH": str(length if length is not None else len(body)), "wsgi.input": io.BytesIO(body)}, lambda status, headers: statuses.append(status))
        return statuses[0], json.loads(b"".join(result))

    def test_health(self):
        self.assertEqual(self.request("/health"), ("200 OK", {"status": "ok"}))

    def test_upload_list_detail_and_persistence(self):
        status, log = self.request("/logs", "POST", {"filename": "api.txt", "content": "ERROR timeout\nWARN retry\nINFO ready"})
        self.assertEqual(status, "201 Created")
        self.assertEqual((log["error_count"], log["warning_count"]), (1, 1))
        self.app = create_app(self.database)
        self.assertEqual(self.request("/logs")[1][0]["id"], log["id"])
        self.assertEqual(self.request("/logs/" + log["id"])[1]["content"], log["content"])

    def test_reject_invalid_uploads(self):
        for payload in [{"filename": "bad.exe", "content": "hello"}, {"filename": "../a.txt", "content": "hello"}, {"filename": "a.txt", "content": " "}, {"filename": "a.txt", "content": 12}, []]:
            with self.subTest(payload=payload):
                self.assertEqual(self.request("/logs", "POST", payload)[0], "400 Bad Request")
        self.assertEqual(self.request("/logs", "POST", raw=b"invalid")[0], "400 Bad Request")
        self.assertEqual(self.request("/logs", "POST", raw=b"\xff")[0], "400 Bad Request")

    def test_size_limit(self):
        self.assertEqual(self.request("/logs", "POST", raw=b"x", length=1048577)[0], "413 Payload Too Large")

    def test_missing_log(self):
        self.assertEqual(self.request("/logs/missing")[0], "404 Not Found")


if __name__ == "__main__":
    unittest.main()
