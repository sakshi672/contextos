"""Exercise the first persistent save-and-retrieve workflow over HTTP."""

import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server import db
from server.app import Handler


class MemoryApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        db.DB_PATH = Path(cls.temp.name) / "memories.db"
        db.initialize()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temp.cleanup()

    def call(self, path, method="GET", body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = Request(self.base + path, data=data, method=method,
                      headers={"Content-Type": "application/json"})
        try:
            with urlopen(req, timeout=3) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            return error.code, json.load(error)

    def test_save_search_edit_delete_persists(self):
        status, saved = self.call("/api/memories", "POST", {
            "kind": "link", "title": "A useful article", "source_url": "https://example.com/article",
            "note": "Our telescope research reference",
        })
        self.assertEqual(status, 201)
        memory_id = saved["id"]
        self.assertEqual(self.call(f"/api/memories/{memory_id}")[1]["title"], "A useful article")
        found = self.call("/api/memories?q=telescope")[1]["items"]
        self.assertEqual([item["id"] for item in found], [memory_id])
        self.assertEqual(self.call("/api/memories?kind=note")[1]["items"], [])

        status, updated = self.call(f"/api/memories/{memory_id}", "PUT", {
            "kind": "link", "title": "Renamed article", "source_url": "https://example.com/article",
            "note": "About observatories",
        })
        self.assertEqual(status, 200)
        self.assertEqual(updated["title"], "Renamed article")
        self.assertEqual(self.call("/api/memories?q=telescope")[1]["items"], [])
        self.assertEqual(len(self.call("/api/memories?q=observatories")[1]["items"]), 1)

        self.assertEqual(self.call(f"/api/memories/{memory_id}", "DELETE")[0], 200)
        self.assertEqual(self.call(f"/api/memories/{memory_id}")[0], 404)
        self.assertEqual(self.call("/api/memories?q=observatories")[1]["items"], [])

    def test_invalid_url_is_rejected(self):
        status, result = self.call("/api/memories", "POST", {
            "kind": "link", "title": "Unsafe", "source_url": "file:///private/data",
        })
        self.assertEqual(status, 400)
        self.assertIn("URL", result["error"])


if __name__ == "__main__":
    unittest.main()
