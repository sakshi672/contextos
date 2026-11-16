"""Live PostgreSQL API test for account isolation and the first memory flow."""

import http.cookiejar
import json
import socket
import threading
import unittest
import uuid
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

import uvicorn

from backend.contextos.database import connection
from backend.contextos.local_db import ENV_FILE, load_env
from backend.contextos.main import app


class PostgresApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ENV_FILE.exists():
            raise unittest.SkipTest("Local PostgreSQL settings unavailable")
        load_env()
        try:
            with connection() as db:
                db.execute("SELECT 1")
        except Exception as exc:
            raise unittest.SkipTest(f"Local PostgreSQL unavailable: {exc}") from exc
        cls.socket = socket.socket()
        cls.socket.bind(("127.0.0.1", 0))
        cls.socket.listen(128)
        cls.base = f"http://127.0.0.1:{cls.socket.getsockname()[1]}"
        cls.server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
        cls.thread = threading.Thread(target=cls.server.run, kwargs={"sockets": [cls.socket]}, daemon=True)
        cls.thread.start()
        cls.started_accounts = []

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=5)
        with connection() as db:
            for account_id in cls.started_accounts:
                db.execute("DELETE FROM accounts WHERE id = %s", (account_id,))

    def call(self, opener, path, method="GET", body=None, csrf=None):
        headers = {"Content-Type": "application/json"}
        if csrf:
            headers["X-CSRF-Token"] = csrf
        request = Request(
            self.base + path, method=method, headers=headers,
            data=json.dumps(body).encode() if body is not None else None,
        )
        try:
            response = opener.open(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def register(self):
        opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        email = f"test-{uuid.uuid4()}@example.test"
        status, result = self.call(opener, "/v1/auth/register", "POST", {
            "email": email, "password": "test-password-very-long",
        })
        self.assertEqual(status, 201, result)
        self.started_accounts.append(result["data"]["id"])
        return opener, result["data"]["csrf_token"]

    def test_owned_memory_flow_and_csrf(self):
        first, first_csrf = self.register()
        second, second_csrf = self.register()
        status, result = self.call(first, "/v1/memories", "POST", {
            "kind": "link", "title": "A useful article",
            "source_uri": "https://example.com/article", "user_note": "Telescope research",
        }, first_csrf)
        self.assertEqual(status, 201, result)
        memory_id = result["data"]["id"]
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}")[0], 200)
        self.assertEqual(len(self.call(first, "/v1/memories")[1]["data"]["items"]), 1)
        self.assertEqual(len(self.call(first, "/v1/memories?q=telescope")[1]["data"]["items"]), 1)
        self.assertEqual(self.call(first, "/v1/memories?q=missing")[1]["data"]["items"], [])
        self.assertEqual(self.call(second, "/v1/memories")[1]["data"]["items"], [])
        self.assertEqual(self.call(second, f"/v1/memories/{memory_id}")[0], 404)
        self.assertEqual(self.call(second, f"/v1/memories/{memory_id}", "DELETE", csrf=second_csrf)[0], 404)
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}", "PATCH", {"title": "Changed"})[0], 403)
        status, updated = self.call(first, f"/v1/memories/{memory_id}", "PATCH", {"title": "Changed"}, first_csrf)
        self.assertEqual(status, 200, updated)
        self.assertEqual(updated["data"]["title"], "Changed")
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}", "DELETE", csrf=first_csrf)[0], 200)
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}")[0], 404)
        self.assertEqual(self.call(first, "/v1/auth/logout", "POST", csrf=first_csrf)[0], 200)
        self.assertEqual(self.call(first, "/v1/memories")[0], 401)

    def test_login_and_session_recovery(self):
        anonymous = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.assertEqual(self.call(anonymous, "/v1/auth/session")[0], 401)
        first, csrf = self.register()
        status, session = self.call(first, "/v1/auth/session")
        self.assertEqual(status, 200, session)
        self.assertEqual(session["data"]["csrf_token"], csrf)
        self.assertEqual(self.call(first, "/v1/auth/logout", "POST", csrf=csrf)[0], 200)
        status, result = self.call(first, "/v1/auth/login", "POST", {
            "email": session["data"]["email"], "password": "test-password-very-long",
        })
        self.assertEqual(status, 200, result)
        self.assertEqual(result["data"]["id"], session["data"]["id"])
        self.assertEqual(self.call(first, "/v1/auth/session")[0], 200)


if __name__ == "__main__":
    unittest.main()
