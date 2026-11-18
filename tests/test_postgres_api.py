"""Live PostgreSQL API test for account isolation and the first memory flow."""

import http.cookiejar
import base64
import hashlib
from io import BytesIO
import json
import os
import socket
import tempfile
import threading
import unittest
import uuid
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener
from urllib.parse import quote
from zipfile import ZipFile
from unittest.mock import patch

import uvicorn
import psycopg
from psycopg import sql
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from PIL import Image, ImageDraw, ImageFont

from backend.contextos.database import connection
from backend.contextos.local_db import ENV_FILE, load_env
from backend.contextos.migrate import migrate
from backend.contextos.jobs import claim_one, finish
from backend.contextos.main import app
from backend.contextos.storage import path_for
from backend.contextos.worker import run_once
from backend.contextos.extract_text import handle as extract_text
from backend.contextos.manual_urls import checked_url, public_address, fetch_page


class PostgresApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ENV_FILE.exists():
            raise unittest.SkipTest("Local PostgreSQL settings unavailable")
        load_env()
        cls.database_url = os.environ["CONTEXT_OS_DATABASE_URL"]
        cls.previous_pgoptions = os.environ.get("PGOPTIONS")
        cls.schema = f"contextos_test_{uuid.uuid4().hex}"
        try:
            with psycopg.connect(cls.database_url) as db:
                db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(cls.schema)))
        except Exception as exc:
            raise unittest.SkipTest(f"Could not create isolated PostgreSQL test schema: {exc}") from exc
        os.environ["PGOPTIONS"] = f"-c search_path={cls.schema}"
        cls.storage = tempfile.TemporaryDirectory()
        os.environ["CONTEXT_OS_STORAGE_ROOT"] = cls.storage.name
        try:
            migrate()
            with connection() as db:
                db.execute("SELECT 1")
        except Exception as exc:
            cls._release_test_schema()
            raise unittest.SkipTest(f"Local PostgreSQL test schema unavailable: {exc}") from exc
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
        cls.socket.close()
        os.environ.pop("CONTEXT_OS_STORAGE_ROOT", None)
        cls.storage.cleanup()
        cls._release_test_schema()

    @classmethod
    def _release_test_schema(cls):
        if cls.previous_pgoptions is None:
            os.environ.pop("PGOPTIONS", None)
        else:
            os.environ["PGOPTIONS"] = cls.previous_pgoptions
        # Only the exact schema generated for this test run may be dropped.
        if cls.schema.startswith("contextos_test_") and len(cls.schema) == len("contextos_test_") + 32:
            with psycopg.connect(cls.database_url) as db:
                db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(cls.schema)))

    def call(self, opener, path, method="GET", body=None, csrf=None, bearer=None, idempotency_key=None):
        headers = {"Content-Type": "application/json"}
        if csrf:
            headers["X-CSRF-Token"] = csrf
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
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

    def extract_test_document(self, account_id, memory_id):
        extract_text({"memory_id": uuid.UUID(str(memory_id)), "account_id": uuid.UUID(str(account_id))})

    def test_ranked_search_indexes_content_metadata_and_isolates_accounts(self):
        first, csrf = self.register()
        second, second_csrf = self.register()
        title = self.call(first, "/v1/memories", "POST", {
            "kind": "note", "title": "Telescope planning", "user_note": "Observing schedule",
        }, csrf)[1]["data"]["id"]
        content = self.call(first, "/v1/memories", "POST", {
            "kind": "snippet", "title": "Night journal", "body": "We carried a telescope to the hill.",
        }, csrf)[1]["data"]["id"]
        source = self.call(first, "/v1/memories", "POST", {
            "kind": "link", "title": "Observatory", "source_uri": "https://astronomy.example.test/guide",
        }, csrf)[1]["data"]["id"]
        self.call(second, "/v1/memories", "POST", {
            "kind": "note", "title": "Telescope belonging to another account",
        }, second_csrf)

        status, result = self.call(first, "/v1/search?q=telescope")
        self.assertEqual(status, 200, result)
        self.assertEqual(result["data"]["total"], 2)
        self.assertEqual([item["id"] for item in result["data"]["items"]], [title, content])
        self.assertIn("title", result["data"]["items"][0]["match_reasons"])
        self.assertIn("content", result["data"]["items"][1]["match_reasons"])
        self.assertIn("[telescope]", result["data"]["items"][1]["snippet"].lower())
        self.assertEqual(self.call(second, "/v1/search?q=telescope")[1]["data"]["total"], 1)
        self.assertEqual(self.call(first, "/v1/search?q=astronomy")[1]["data"]["items"][0]["id"], source)
        self.assertEqual(self.call(first, "/v1/search?q=telescope&kind=snippet")[1]["data"]["items"][0]["id"], content)
        self.assertEqual(self.call(first, "/v1/search?q=telescope&domain=astronomy.example.test")[1]["data"]["total"], 0)
        self.assertEqual(self.call(first, "/v1/search?q=telescope&date_from=2099-01-01")[1]["data"]["total"], 0)
        project_id = uuid.uuid4()
        with connection() as db:
            account_id = self.started_accounts[-2]
            db.execute("INSERT INTO projects (id, account_id, name) VALUES (%s, %s, %s)",
                       (project_id, account_id, "Sky study"))
            db.execute("INSERT INTO memory_projects (memory_id, project_id, account_id) VALUES (%s, %s, %s)",
                       (title, project_id, account_id))
        self.assertEqual(self.call(first, f"/v1/search?q=telescope&project_id={project_id}")[1]["data"]["items"][0]["id"], title)
        self.assertEqual(self.call(second, f"/v1/search?q=telescope&project_id={project_id}")[1]["data"]["total"], 0)
        self.assertEqual(self.call(first, f"/v1/search?project_id={project_id}")[1]["data"]["items"][0]["id"], title)
        status, partial = self.call(first, "/v1/search?q=telescope%20unrelated")
        self.assertEqual(status, 200, partial)
        self.assertEqual(partial["data"]["match_mode"], "some_words")
        self.assertEqual(partial["data"]["items"][0]["id"], title)

        self.call(first, f"/v1/memories/{title}", "PATCH", {"title": "Meteor planning"}, csrf)
        self.assertEqual(self.call(first, "/v1/search?q=telescope")[1]["data"]["total"], 1)
        self.call(first, f"/v1/memories/{content}", "DELETE", csrf=csrf)
        self.assertEqual(self.call(first, "/v1/search?q=telescope")[1]["data"]["total"], 0)

    def test_organization_crud_multi_assignment_and_search_filters(self):
        first, csrf = self.register()
        second, other_csrf = self.register()
        memory_id = self.call(first, "/v1/memories", "POST", {
            "kind": "note", "title": "Aurora observations", "user_note": "Northern lights",
        }, csrf)[1]["data"]["id"]

        def create(entity, name):
            status, result = self.call(first, f"/v1/organization/{entity}", "POST", {"name": name}, csrf)
            self.assertEqual(status, 201, result)
            return result["data"]["id"]

        project_a = create("projects", "Sky study")
        project_b = create("projects", "Travel")
        tag_id = create("tags", "Astronomy")
        collection_id = create("collections", "Ideas")
        self.assertEqual(self.call(first, "/v1/organization/tags", "POST", {"name": "astronomy"}, csrf)[0], 409)
        self.assertEqual(self.call(second, f"/v1/organization/projects/{project_a}", "PATCH", {"name": "Stolen"}, other_csrf)[0], 404)
        self.assertEqual(self.call(second, "/v1/organization")[1]["data"]["projects"], [])
        payload = {"project_ids": [project_a, project_b], "tag_ids": [tag_id],
                   "collection_ids": [collection_id]}
        status, result = self.call(first, f"/v1/organization/memories/{memory_id}", "PUT", payload, csrf)
        self.assertEqual(status, 200, result)
        self.assertEqual(len(result["data"]["projects"]), 2)
        self.assertEqual(self.call(second, f"/v1/organization/memories/{memory_id}", "PUT", payload, other_csrf)[0], 404)
        self.assertEqual(len(self.call(first, f"/v1/memories/{memory_id}")[1]["data"]["organization"]["projects"]), 2)
        for key, value in (("project_id", project_a), ("project_id", project_b),
                           ("tag_id", tag_id), ("collection_id", collection_id)):
            self.assertEqual(self.call(first, f"/v1/search?q=aurora&{key}={value}")[1]["data"]["total"], 1)
            self.assertEqual(self.call(second, f"/v1/search?q=aurora&{key}={value}")[1]["data"]["total"], 0)
        self.assertEqual(self.call(first, f"/v1/organization/projects/{project_a}", "PATCH", {"name": "Night sky"}, csrf)[1]["data"]["name"], "Night sky")
        self.assertEqual(self.call(first, f"/v1/organization/tags/{tag_id}", "DELETE", csrf=csrf)[0], 200)
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}")[1]["data"]["organization"]["tags"], [])
        self.assertEqual(self.call(first, f"/v1/organization/collections/{collection_id}", "DELETE", csrf=csrf)[0], 200)

    def test_search_returns_matching_pdf_page_and_ignores_inactive_content(self):
        user, _ = self.register()
        account_id = self.started_accounts[-1]
        memory_id, content_id = uuid.uuid4(), uuid.uuid4()
        body = "A nebula appears near the horizon."
        with connection() as db:
            db.execute("""INSERT INTO memories (id, account_id, kind, title, captured_at, status)
                VALUES (%s, %s, 'pdf', 'Field notebook', now(), 'ready')""", (memory_id, account_id))
            db.execute("""INSERT INTO memory_contents (id, account_id, memory_id, version, provenance,
                body, content_sha256, status, is_active) VALUES (%s, %s, %s, 1, 'extracted', %s, %s, 'ready', true)""",
                (content_id, account_id, memory_id, body, hashlib.sha256(body.encode()).hexdigest()))
            db.execute("""INSERT INTO content_passages (id, account_id, memory_id, content_id, ordinal,
                body, page_number) VALUES (%s, %s, %s, %s, 0, %s, 7)""",
                (uuid.uuid4(), account_id, memory_id, content_id, body))
        status, result = self.call(user, "/v1/search?q=nebula")
        self.assertEqual(status, 200, result)
        self.assertEqual(result["data"]["items"][0]["page_number"], 7)
        self.assertIn("content", result["data"]["items"][0]["match_reasons"])
        with connection() as db:
            db.execute("UPDATE memory_contents SET is_active = false WHERE id = %s", (content_id,))
        self.assertEqual(self.call(user, "/v1/search?q=nebula")[1]["data"]["total"], 0)

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

    def test_password_recovery_is_one_time_and_revokes_sessions(self):
        user, csrf = self.register()
        account_id = self.started_accounts[-1]
        email = self.call(user, "/v1/auth/session")[1]["data"]["email"]
        delivered = []
        with patch("backend.contextos.recovery.deliver", side_effect=lambda address, token, mode: delivered.append((address, token, mode))):
            status, result = self.call(user, "/v1/auth/recover/request", "POST", {"email": email})
            self.assertEqual(status, 200, result)
            self.assertNotIn("token", json.dumps(result))
            self.assertEqual(self.call(user, "/v1/auth/recover/request", "POST", {"email": email})[0], 200)
            self.assertEqual(self.call(user, "/v1/auth/recover/request", "POST", {"email": "unknown@example.test"})[0], 200)
        self.assertEqual(len(delivered), 1)
        self.assertEqual(delivered[0][0], email)
        self.assertEqual(delivered[0][2], "local")
        token = delivered[0][1]
        status, result = self.call(user, "/v1/auth/recover/reset", "POST", {
            "token": token, "password": "a-different-long-password",
        })
        self.assertEqual(status, 200, result)
        self.assertEqual(self.call(user, "/v1/auth/session")[0], 401)
        self.assertEqual(self.call(user, "/v1/auth/recover/reset", "POST", {
            "token": token, "password": "another-long-password",
        })[0], 400)
        self.assertEqual(self.call(user, "/v1/auth/login", "POST", {
            "email": email, "password": "test-password-very-long",
        })[0], 401)
        self.assertEqual(self.call(user, "/v1/auth/login", "POST", {
            "email": email, "password": "a-different-long-password",
        })[0], 200)
        with connection() as db:
            verified = db.execute("SELECT email_verified_at FROM accounts WHERE id = %s", (account_id,)).fetchone()
        self.assertIsNotNone(verified["email_verified_at"])

    def test_invalid_email_is_rejected_before_recovery_delivery(self):
        user = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        with patch("backend.contextos.recovery.deliver") as delivery:
            status, _ = self.call(user, "/v1/auth/recover/request", "POST",
                                  {"email": "person@example.test\nBcc:other@example.test"})
            self.assertEqual(status, 422)
            delivery.assert_not_called()

    def test_text_upload_extract_and_private_download(self):
        first, first_csrf = self.register()
        first_account = self.started_accounts[-1]
        second, second_csrf = self.register()
        content = "A café note about telescope research.\n".encode("utf-8")
        request = Request(
            self.base + "/v1/uploads/text?filename=" + quote("research.md"),
            data=content, method="POST",
            headers={"Content-Type": "text/markdown", "X-CSRF-Token": first_csrf},
        )
        with first.open(request, timeout=5) as response:
            self.assertEqual(response.status, 201)
            result = json.load(response)
        memory_id = result["data"]["id"]
        self.assertEqual(result["data"]["status"], "pending")
        self.assertEqual(self.call(second, f"/v1/memories/{memory_id}/content")[0], 404)
        self.assertEqual(self.call(second, f"/v1/uploads/{memory_id}/original")[0], 404)
        with first.open(self.base + f"/v1/uploads/{memory_id}/original", timeout=5) as response:
            self.assertEqual(response.read(), content)
        self.extract_test_document(first_account, memory_id)
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}")[1]["data"]["status"], "ready")
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}/content")[1]["data"]["body"], content.decode())
        with connection() as db:
            key = db.execute("SELECT object_key FROM memory_assets WHERE memory_id = %s", (memory_id,)).fetchone()["object_key"]
        self.assertTrue(path_for(key).is_file())
        self.assertEqual(self.call(second, f"/v1/memories/{memory_id}", "DELETE", csrf=second_csrf)[0], 404)
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}", "DELETE", csrf=first_csrf)[0], 200)
        self.assertFalse(path_for(key).exists())
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}/content")[0], 404)

    def test_invalid_text_upload_rejected_and_corrupt_original_reports_failure(self):
        first, csrf = self.register()
        account_id = self.started_accounts[-1]
        unsupported = Request(
            self.base + "/v1/uploads/text?filename=unsafe.exe", data=b"text", method="POST",
            headers={"X-CSRF-Token": csrf},
        )
        with self.assertRaises(HTTPError) as error:
            first.open(unsupported, timeout=5)
        self.assertEqual(error.exception.code, 415)

        payload = b"\xff\xfe\x00"
        invalid = Request(
            self.base + "/v1/uploads/text?filename=broken.txt", data=payload, method="POST",
            headers={"X-CSRF-Token": csrf},
        )
        with self.assertRaises(HTTPError) as error:
            first.open(invalid, timeout=5)
        self.assertEqual(error.exception.code, 422)
        self.assertEqual(self.call(first, "/v1/memories?kind=document")[1]["data"]["total"], 0)

        valid = Request(self.base + "/v1/uploads/text?filename=broken.txt", data=b"valid text",
                        method="POST", headers={"X-CSRF-Token": csrf})
        with first.open(valid, timeout=5) as response:
            memory_id = json.load(response)["data"]["id"]
        with connection() as db:
            key = db.execute("SELECT object_key FROM memory_assets WHERE memory_id = %s",
                             (memory_id,)).fetchone()["object_key"]
        path_for(key).write_bytes(payload)
        self.assertTrue(run_once(account_id=account_id))
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}")[1]["data"]["status"], "failed")
        with connection() as db:
            job = db.execute("SELECT status, error_code FROM extraction_jobs WHERE memory_id = %s", (memory_id,)).fetchone()
        self.assertEqual((job["status"], job["error_code"]), ("failed", "checksum_mismatch"))
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}/content")[0], 404)
        with first.open(self.base + f"/v1/uploads/{memory_id}/original", timeout=5) as response:
            self.assertEqual(response.read(), payload)
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}", "DELETE", csrf=csrf)[0], 200)

    def test_missing_original_marks_job_failed_without_retrying(self):
        first, csrf = self.register()
        account_id = self.started_accounts[-1]
        request = Request(self.base + "/v1/uploads/text?filename=missing.txt", data=b"test",
                          method="POST", headers={"X-CSRF-Token": csrf})
        with first.open(request, timeout=5) as response:
            memory_id = json.load(response)["data"]["id"]
        with connection() as db:
            key = db.execute("SELECT object_key FROM memory_assets WHERE memory_id = %s",
                             (memory_id,)).fetchone()["object_key"]
        path_for(key).unlink()
        self.assertTrue(run_once(account_id=account_id))
        with connection() as db:
            job = db.execute("SELECT status, error_code FROM extraction_jobs WHERE memory_id = %s",
                             (memory_id,)).fetchone()
        self.assertEqual((job["status"], job["error_code"]), ("failed", "missing_original_file"))
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}")[1]["data"]["status"], "failed")
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}", "DELETE", csrf=csrf)[0], 200)

    def test_expired_final_lease_and_stale_completion(self):
        first, csrf = self.register()
        account_id = self.started_accounts[-1]
        request = Request(
            self.base + "/v1/uploads/text?filename=lease.txt", data=b"safe text", method="POST",
            headers={"X-CSRF-Token": csrf},
        )
        with first.open(request, timeout=5) as response:
            memory_id = json.load(response)["data"]["id"]
        with connection() as db:
            job_id = db.execute(
                "UPDATE extraction_jobs SET status = 'processing', attempt_count = 3, "
                "lease_until = now() + interval '1 hour' "
                "WHERE memory_id = %s RETURNING id", (memory_id,),
            ).fetchone()["id"]
        finish(job_id, account_id, 2, error_code="stale_attempt", permanent=True)
        with connection() as db:
            state = db.execute("SELECT status FROM extraction_jobs WHERE id = %s", (job_id,)).fetchone()
            self.assertEqual(state["status"], "processing")
            db.execute("UPDATE extraction_jobs SET lease_until = now() - interval '1 second' WHERE id = %s", (job_id,))
        self.assertIsNone(claim_one(account_id=account_id))
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}")[1]["data"]["status"], "failed")
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}", "DELETE", csrf=csrf)[0], 200)

    def test_account_export_contains_only_owned_records_and_originals(self):
        first, csrf = self.register()
        first_account = self.started_accounts[-1]
        second, second_csrf = self.register()
        self.call(second, "/v1/memories", "POST", {
            "kind": "note", "title": "Another account's secret", "user_note": "private",
        }, second_csrf)
        self.call(first, "/v1/memories", "POST", {
            "kind": "note", "title": "My note", "user_note": "My own words",
        }, csrf)
        original = "Export café source".encode("utf-8")
        request = Request(
            self.base + "/v1/uploads/text?filename=source.txt", data=original, method="POST",
            headers={"X-CSRF-Token": csrf},
        )
        with first.open(request, timeout=5) as response:
            document_id = json.load(response)["data"]["id"]
        self.extract_test_document(first_account, document_id)
        with first.open(self.base + "/v1/export", timeout=5) as response:
            archive_bytes = response.read()
        with ZipFile(BytesIO(archive_bytes)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            memories = [json.loads(line) for line in archive.read("memories.jsonl").splitlines()]
            assets = [json.loads(line) for line in archive.read("assets.jsonl").splitlines()]
            contents = [json.loads(line) for line in archive.read("contents.jsonl").splitlines()]
            self.assertEqual(manifest["memory_count"], 2)
            self.assertEqual({item["title"] for item in memories}, {"My note", "source"})
            self.assertEqual(len(assets), 1)
            self.assertNotIn("object_key", assets[0])
            self.assertEqual(archive.read(assets[0]["path"]), original)
            self.assertEqual(contents[0]["body"], original.decode())
        self.assertEqual(self.call(first, f"/v1/memories/{document_id}", "DELETE", csrf=csrf)[0], 200)

    def test_library_count_sort_and_pages_are_account_scoped(self):
        first, csrf = self.register()
        second, second_csrf = self.register()
        ids = []
        for title in ("Bravo", "Alpha"):
            status, result = self.call(first, "/v1/memories", "POST", {
                "kind": "note", "title": title, "user_note": "research",
            }, csrf)
            self.assertEqual(status, 201)
            ids.append(result["data"]["id"])
        self.call(second, "/v1/memories", "POST", {
            "kind": "note", "title": "Other", "user_note": "research",
        }, second_csrf)
        first_page = self.call(first, "/v1/memories?sort=title&limit=1&offset=0")[1]["data"]
        second_page = self.call(first, "/v1/memories?sort=title&limit=1&offset=1")[1]["data"]
        self.assertEqual(first_page["total"], 2)
        self.assertEqual([first_page["items"][0]["title"], second_page["items"][0]["title"]],
                         ["Alpha", "Bravo"])
        self.assertEqual(self.call(first, "/v1/memories?q=other")[1]["data"]["total"], 0)
        for memory_id in ids:
            self.assertEqual(self.call(first, f"/v1/memories/{memory_id}", "DELETE", csrf=csrf)[0], 200)

    def test_export_round_trip_and_duplicate_report(self):
        source, source_csrf = self.register()
        source_account = self.started_accounts[-1]
        target, target_csrf = self.register()
        self.call(source, "/v1/memories", "POST", {
            "kind": "link", "title": "Research", "source_uri": "https://example.com/research",
            "user_note": "Read later",
        }, source_csrf)
        original = b"Imported source text"
        request = Request(self.base + "/v1/uploads/text?filename=source.md", data=original,
                          method="POST", headers={"X-CSRF-Token": source_csrf})
        with source.open(request, timeout=5) as response:
            json.load(response)
        with connection() as db:
            source_document = db.execute("SELECT id FROM memories WHERE account_id = %s AND kind = 'document'",
                                         (source_account,)).fetchone()["id"]
        self.extract_test_document(source_account, source_document)
        with source.open(self.base + "/v1/export", timeout=5) as response:
            archive = response.read()
        request = Request(self.base + "/v1/import?format=contextos", data=archive,
                          method="POST", headers={"X-CSRF-Token": target_csrf,
                                                  "Content-Type": "application/zip"})
        with target.open(request, timeout=5) as response:
            report = json.load(response)["data"]
        self.assertEqual((report["imported"], report["duplicates"], report["failed"]), (2, 0, 0), report)
        document_id = next(item["memory_id"] for item in report["items"] if
                           self.call(target, f"/v1/memories/{item['memory_id']}")[1]["data"]["kind"] == "document")
        with target.open(self.base + f"/v1/uploads/{document_id}/original", timeout=5) as response:
            self.assertEqual(response.read(), original)
        self.assertEqual(self.call(target, f"/v1/memories/{document_id}/content")[1]["data"]["body"],
                         original.decode())
        with target.open(request, timeout=5) as response:
            repeated = json.load(response)["data"]
        self.assertEqual((repeated["imported"], repeated["duplicates"], repeated["failed"]), (0, 2, 0))

    def test_bookmark_import_reports_invalid_and_duplicate_urls(self):
        user, csrf = self.register()
        html = b'<DL><DT><A HREF="https://example.com/one" ADD_DATE="1700000000">One</A>' \
               b'<DT><A HREF="javascript:alert(1)">Unsafe</A>' \
               b'<DT><A HREF="https://example.com/one">Repeat</A></DL>'
        request = Request(self.base + "/v1/import?format=bookmarks", data=html,
                          method="POST", headers={"X-CSRF-Token": csrf})
        with user.open(request, timeout=5) as response:
            report = json.load(response)["data"]
        self.assertEqual((report["imported"], report["duplicates"], report["failed"]), (1, 1, 1), report)
        self.assertEqual(self.call(user, "/v1/memories")[1]["data"]["total"], 1)

    def test_export_import_round_trip_preserves_multi_organization(self):
        source, csrf = self.register()
        target, target_csrf = self.register()
        memory_id = self.call(source, "/v1/memories", "POST", {
            "kind": "note", "title": "Constellation map", "user_note": "Orion and Lyra",
        }, csrf)[1]["data"]["id"]
        def create(entity, name):
            return self.call(source, f"/v1/organization/{entity}", "POST", {"name": name}, csrf)[1]["data"]["id"]
        first_project = create("projects", "Research")
        second_project = create("projects", "Travel")
        tag = create("tags", "Sky")
        collection = create("collections", "Favorites")
        create("collections", "Empty collection")
        payload = {"project_ids": [first_project, second_project], "tag_ids": [tag],
                   "collection_ids": [collection]}
        self.assertEqual(self.call(source, f"/v1/organization/memories/{memory_id}", "PUT", payload, csrf)[0], 200)
        with source.open(self.base + "/v1/export", timeout=5) as response:
            archive = response.read()
        with ZipFile(BytesIO(archive)) as bundle:
            self.assertEqual(json.loads(bundle.read("manifest.json"))["version"], 2)
        request = Request(self.base + "/v1/import?format=contextos", data=archive, method="POST",
                          headers={"X-CSRF-Token": target_csrf, "Content-Type": "application/zip"})
        with target.open(request, timeout=5) as response:
            report = json.load(response)["data"]
        self.assertEqual((report["imported"], report["failed"]), (1, 0), report)
        imported_id = report["items"][0]["memory_id"]
        assigned = self.call(target, f"/v1/memories/{imported_id}")[1]["data"]["organization"]
        self.assertEqual({item["name"] for item in assigned["projects"]}, {"Research", "Travel"})
        self.assertEqual([item["name"] for item in assigned["tags"]], ["Sky"])
        self.assertEqual([item["name"] for item in assigned["collections"]], ["Favorites"])
        self.assertEqual(len(self.call(target, "/v1/organization")[1]["data"]["collections"]), 2)

    def test_import_rejects_bad_archives_without_creating_records(self):
        user, csrf = self.register()
        for payload in (b"not a zip", self._archive_with_unsafe_path()):
            request = Request(self.base + "/v1/import?format=contextos", data=payload,
                              method="POST", headers={"X-CSRF-Token": csrf})
            with self.assertRaises(HTTPError) as error:
                user.open(request, timeout=5)
            self.assertEqual(error.exception.code, 422)
        self.assertEqual(self.call(user, "/v1/memories")[1]["data"]["total"], 0)

    @staticmethod
    def _archive_with_unsafe_path():
        output = BytesIO()
        with ZipFile(output, "w") as archive:
            archive.writestr("../outside", "bad")
            archive.writestr("manifest.json", json.dumps({"format": "contextos-account-export", "version": 1,
                                                          "memory_count": 0, "content_count": 0, "asset_count": 0}))
            for name in ("memories.jsonl", "contents.jsonl", "assets.jsonl"):
                archive.writestr(name, "")
        return output.getvalue()

    def test_file_cleanup_retries_after_unlink_failure(self):
        user, csrf = self.register()
        account_id = self.started_accounts[-1]
        request = Request(self.base + "/v1/uploads/text?filename=cleanup.txt", data=b"keep until retry",
                          method="POST", headers={"X-CSRF-Token": csrf})
        with user.open(request, timeout=5) as response:
            memory_id = json.load(response)["data"]["id"]
        with connection() as db:
            key = db.execute("SELECT object_key FROM memory_assets WHERE memory_id = %s",
                             (memory_id,)).fetchone()["object_key"]
        with patch("backend.contextos.object_cleanup.delete_object", side_effect=OSError("locked")):
            self.assertEqual(self.call(user, f"/v1/memories/{memory_id}", "DELETE", csrf=csrf)[0], 200)
        self.assertTrue(path_for(key).exists())
        with connection() as db:
            self.assertEqual(db.execute("SELECT count(*) AS n FROM object_deletions WHERE object_key = %s",
                                        (key,)).fetchone()["n"], 1)
            db.execute("UPDATE object_deletions SET next_retry_at = now() WHERE object_key = %s", (key,))
        self.assertTrue(run_once(account_id=account_id))
        self.assertFalse(path_for(key).exists())
        with connection() as db:
            self.assertEqual(db.execute("SELECT count(*) AS n FROM object_deletions WHERE object_key = %s",
                                        (key,)).fetchone()["n"], 0)

    def test_extension_pairing_capture_duplicate_project_and_revocation(self):
        first, csrf = self.register()
        second, second_csrf = self.register()
        status, result = self.call(first, "/v1/extension/pairings", "POST", csrf=csrf)
        self.assertEqual(status, 201, result)
        code = result["data"]["code"]
        self.assertEqual(self.call(first, "/v1/extension/pairings", "POST")[0], 403)
        status, exchange = self.call(first, "/v1/extension/tokens", "POST", {"code": code})
        self.assertEqual(status, 200, exchange)
        token = exchange["data"]["token"]
        self.assertEqual(self.call(first, "/v1/extension/tokens", "POST", {"code": code})[0], 401)
        self.assertEqual(self.call(first, "/v1/extension/session", bearer=token)[0], 200)
        payload = {"source_url": "https://example.com/story", "title": "Story",
                   "readable_text": "Visible story text", "user_note": "Read later", "project_name": "Research"}
        status, captured = self.call(first, "/v1/captures", "POST", payload, bearer=token)
        self.assertEqual(status, 201, captured)
        memory_id = captured["data"]["memory"]["id"]
        self.assertFalse(captured["data"]["already_saved"])
        self.assertTrue(captured["data"]["text_saved"])
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}/content")[1]["data"]["body"], "Visible story text")
        self.assertEqual(self.call(second, f"/v1/memories/{memory_id}")[0], 404)
        status, repeated = self.call(first, "/v1/captures", "POST", payload, bearer=token)
        self.assertTrue(repeated["data"]["already_saved"])
        self.assertEqual(repeated["data"]["memory"]["id"], memory_id)
        self.assertEqual(self.call(first, "/v1/extension/projects", bearer=token)[1]["data"]["names"], ["Research"])
        status, edited = self.call(first, f"/v1/extension/captures/{memory_id}", "PATCH",
                                   {"user_note": "Updated", "project_name": "Work"}, bearer=token)
        self.assertEqual(status, 200, edited)
        self.assertEqual(edited["data"]["project_name"], "Work")
        self.assertEqual(edited["data"]["memory"]["user_note"], "Updated")
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/pZkAAAAASUVORK5CYII=")
        request = Request(self.base + f"/v1/extension/captures/{memory_id}/screenshot", data=png,
                          method="POST", headers={"Authorization": f"Bearer {token}", "Content-Type": "image/png"})
        with first.open(request, timeout=5) as response:
            self.assertEqual(response.status, 201)
        with first.open(self.base + f"/v1/uploads/{memory_id}/screenshot", timeout=5) as response:
            self.assertEqual(response.read(), png)
        self.assertEqual(self.call(second, f"/v1/uploads/{memory_id}/screenshot")[0], 404)
        with first.open(self.base + "/v1/export", timeout=5) as response:
            archive = response.read()
        request = Request(self.base + "/v1/import?format=contextos", data=archive,
                          method="POST", headers={"X-CSRF-Token": second_csrf, "Content-Type": "application/zip"})
        with second.open(request, timeout=5) as response:
            imported = json.load(response)["data"]
        self.assertEqual((imported["imported"], imported["failed"]), (1, 0), imported)
        imported_id = imported["items"][0]["memory_id"]
        self.assertNotEqual(imported_id, memory_id)
        projects = self.call(second, f"/v1/memories/{imported_id}")[1]["data"]["organization"]["projects"]
        self.assertEqual({item["name"] for item in projects}, {"Research", "Work"})
        self.assertEqual(self.call(second, f"/v1/memories/{imported_id}/content")[1]["data"]["body"], "Visible story text")
        with second.open(self.base + f"/v1/uploads/{imported_id}/screenshot", timeout=5) as response:
            self.assertEqual(response.read(), png)
        self.assertEqual(self.call(first, "/v1/extension/revoke", "POST", bearer=token)[0], 200)
        self.assertEqual(self.call(first, "/v1/extension/session", bearer=token)[0], 401)
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}", "DELETE", csrf=csrf)[0], 200)

    def test_metadata_only_capture_and_invalid_scheme(self):
        first, csrf = self.register()
        code = self.call(first, "/v1/extension/pairings", "POST", csrf=csrf)[1]["data"]["code"]
        token = self.call(first, "/v1/extension/tokens", "POST", {"code": code})[1]["data"]["token"]
        bad = {"source_url": "chrome://settings", "title": "Settings"}
        self.assertEqual(self.call(first, "/v1/captures", "POST", bad, bearer=token)[0], 422)
        status, result = self.call(first, "/v1/captures", "POST", {
            "source_url": "https://example.com/restricted", "title": "Restricted",
            "extraction_reason": "page_access_restricted",
        }, bearer=token)
        self.assertEqual(status, 201, result)
        memory_id = result["data"]["memory"]["id"]
        self.assertEqual(result["data"]["memory"]["status"], "partial")
        self.assertEqual(result["data"]["memory"]["capture_reason"], "page_access_restricted")
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}")[0], 200)

    def test_capture_retry_idempotency_and_new_content(self):
        user, csrf = self.register()
        code = self.call(user, "/v1/extension/pairings", "POST", csrf=csrf)[1]["data"]["code"]
        token = self.call(user, "/v1/extension/tokens", "POST", {"code": code})[1]["data"]["token"]
        payload = {"source_url": "https://example.com/updated", "title": "Updating page",
                   "extraction_reason": "page_access_restricted"}
        status, first = self.call(user, "/v1/captures", "POST", payload, bearer=token, idempotency_key="first-attempt")
        self.assertEqual(status, 201, first)
        memory_id = first["data"]["memory"]["id"]
        status, repeated = self.call(user, "/v1/captures", "POST", payload, bearer=token,
                                     idempotency_key="first-attempt")
        self.assertEqual(repeated["data"]["memory"]["id"], memory_id)
        self.assertTrue(repeated["data"]["already_saved"])
        changed = {**payload, "readable_text": "New visible text"}
        self.assertEqual(self.call(user, "/v1/captures", "POST", changed, bearer=token,
                                   idempotency_key="first-attempt")[0], 409)
        status, updated = self.call(user, "/v1/captures", "POST", changed, bearer=token,
                                    idempotency_key="second-attempt")
        self.assertEqual(status, 201, updated)
        self.assertNotEqual(updated["data"]["memory"]["id"], memory_id)
        self.assertTrue(updated["data"]["text_saved"])
        self.assertEqual(self.call(user, "/v1/memories?kind=web_page")[1]["data"]["total"], 2)

    def test_pasted_text_capture_edit_search_and_export(self):
        first, csrf = self.register()
        second, other_csrf = self.register()
        payload = {"kind": "snippet", "title": "Workshop excerpt", "body": "An unusual blue telescope",
                   "user_note": "Discuss with team"}
        self.assertEqual(self.call(first, "/v1/memories", "POST", {**payload, "body": "   "}, csrf)[0], 422)
        status, result = self.call(first, "/v1/memories", "POST", payload, csrf)
        self.assertEqual(status, 201, result)
        memory_id = result["data"]["id"]
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}/content")[1]["data"]["body"], payload["body"])
        self.assertEqual(self.call(first, "/v1/memories?q=telescope&kind=snippet")[1]["data"]["total"], 1)
        self.assertEqual(self.call(second, f"/v1/memories/{memory_id}/content")[0], 404)
        status, changed = self.call(first, f"/v1/memories/{memory_id}", "PATCH",
                                    {"body": "A different red telescope", "user_note": "Revised"}, csrf)
        self.assertEqual(status, 200, changed)
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}/content")[1]["data"]["version"], 2)
        self.assertEqual(self.call(first, "/v1/memories?q=blue&kind=snippet")[1]["data"]["total"], 0)
        self.assertEqual(self.call(first, "/v1/memories?q=red&kind=snippet")[1]["data"]["total"], 1)
        with first.open(self.base + "/v1/export", timeout=5) as response:
            archive = response.read()
        request = Request(self.base + "/v1/import?format=contextos", data=archive, method="POST",
                          headers={"X-CSRF-Token": other_csrf, "Content-Type": "application/zip"})
        with second.open(request, timeout=5) as response:
            report = json.load(response)["data"]
        self.assertEqual((report["imported"], report["failed"]), (1, 0), report)
        restored = report["items"][0]["memory_id"]
        self.assertEqual(self.call(second, f"/v1/memories/{restored}/content")[1]["data"]["body"],
                         "A different red telescope")
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}", "DELETE", csrf=csrf)[0], 200)
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}/content")[0], 404)

    def test_image_upload_preview_isolation_and_export(self):
        first, csrf = self.register()
        second, other_csrf = self.register()
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/pZkAAAAASUVORK5CYII=")
        upload_url = self.base + "/v1/uploads/image?filename=sample.png"
        invalid = Request(upload_url, data=b"not an image", method="POST",
                          headers={"X-CSRF-Token": csrf, "Content-Type": "image/png"})
        with self.assertRaises(HTTPError) as rejected:
            first.open(invalid, timeout=5)
        self.assertEqual(rejected.exception.code, 422)
        request = Request(upload_url, data=png, method="POST",
                          headers={"X-CSRF-Token": csrf, "Content-Type": "image/png"})
        with first.open(request, timeout=5) as response:
            created = json.load(response)["data"]
        memory_id = created["id"]
        self.assertEqual(created["status"], "pending")
        self.assertEqual(self.call(first, "/v1/memories?kind=image")[1]["data"]["total"], 1)
        with first.open(self.base + f"/v1/uploads/{memory_id}/preview", timeout=5) as response:
            self.assertEqual(response.read(), png)
            self.assertEqual(response.headers["Content-Type"], "image/png")
        self.assertEqual(self.call(second, f"/v1/uploads/{memory_id}/preview")[0], 404)
        with first.open(self.base + "/v1/export", timeout=5) as response:
            archive = response.read()
        request = Request(self.base + "/v1/import?format=contextos", data=archive, method="POST",
                          headers={"X-CSRF-Token": other_csrf, "Content-Type": "application/zip"})
        with second.open(request, timeout=5) as response:
            report = json.load(response)["data"]
        self.assertEqual((report["imported"], report["failed"]), (1, 0), report)
        restored = report["items"][0]["memory_id"]
        with second.open(self.base + f"/v1/uploads/{restored}/preview", timeout=5) as response:
            self.assertEqual(response.read(), png)
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}", "DELETE", csrf=csrf)[0], 200)
        self.assertEqual(self.call(first, f"/v1/uploads/{memory_id}/preview")[0], 404)

    def test_pdf_page_extraction_scanned_status_and_export(self):
        first, csrf = self.register()
        second, other_csrf = self.register()
        account_id = self.started_accounts[-2]
        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        stream = DecodedStreamObject()
        stream.set_data(b"BT /F1 14 Tf 72 720 Td (Visible telescope text) Tj ET")
        page[NameObject("/Contents")] = writer._add_object(stream)
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({
            NameObject("/F1"): DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})})})
        writer.add_blank_page(width=612, height=792)
        output = BytesIO()
        writer.write(output)
        pdf = output.getvalue()
        self.assertTrue(pdf.startswith(b"%PDF-"))
        request = Request(self.base + "/v1/uploads/pdf?filename=sample.pdf", data=pdf,
                          method="POST", headers={"X-CSRF-Token": csrf, "Content-Type": "application/pdf"})
        with first.open(request, timeout=5) as response:
            created = json.load(response)["data"]
        memory_id = created["id"]
        self.assertEqual(created["status"], "pending")
        self.assertEqual(self.call(second, f"/v1/uploads/{memory_id}/original")[0], 404)
        self.assertTrue(run_once(account_id=account_id))
        detail = self.call(first, f"/v1/memories/{memory_id}")[1]["data"]
        self.assertEqual(detail["status"], "partial")
        self.assertEqual(detail["capture_reason"], "no_text_detected")
        self.assertEqual(detail["original_asset"]["mime_type"], "application/pdf")
        passages = self.call(first, f"/v1/memories/{memory_id}/passages")[1]["data"]["items"]
        self.assertEqual(len(passages), 1)
        self.assertEqual(passages[0]["page_number"], 1)
        self.assertIn("Visible telescope text", passages[0]["body"])
        self.assertEqual(self.call(first, "/v1/memories?q=telescope&kind=pdf")[1]["data"]["total"], 1)
        self.assertEqual(self.call(second, f"/v1/memories/{memory_id}/passages")[0], 404)
        with first.open(self.base + "/v1/export", timeout=5) as response:
            archive = response.read()
        request = Request(self.base + "/v1/import?format=contextos", data=archive, method="POST",
                          headers={"X-CSRF-Token": other_csrf, "Content-Type": "application/zip"})
        with second.open(request, timeout=5) as response:
            report = json.load(response)["data"]
        self.assertEqual((report["imported"], report["failed"]), (1, 0), report)
        restored = report["items"][0]["memory_id"]
        restored_pages = self.call(second, f"/v1/memories/{restored}/passages")[1]["data"]["items"]
        self.assertEqual(self.call(second, f"/v1/memories/{restored}")[1]["data"]["capture_reason"],
                         "no_text_detected")
        self.assertEqual(restored_pages[0]["page_number"], 1)
        self.assertIn("Visible telescope text", restored_pages[0]["body"])
        corrupt = Request(self.base + "/v1/uploads/pdf?filename=broken.pdf", data=b"%PDF-not-a-real-file",
                          method="POST", headers={"X-CSRF-Token": csrf, "Content-Type": "application/pdf"})
        with first.open(corrupt, timeout=5) as response:
            broken_id = json.load(response)["data"]["id"]
        self.assertTrue(run_once(account_id=account_id))
        self.assertEqual(self.call(first, f"/v1/memories/{broken_id}")[1]["data"]["status"], "failed")
        self.assertEqual(self.call(first, f"/v1/memories/{broken_id}/content")[0], 404)
        ready_writer = PdfWriter()
        ready_writer.add_page(page)
        ready_output = BytesIO()
        ready_writer.write(ready_output)
        request = Request(self.base + "/v1/uploads/pdf?filename=complete.pdf", data=ready_output.getvalue(),
                          method="POST", headers={"X-CSRF-Token": csrf, "Content-Type": "application/pdf"})
        with first.open(request, timeout=5) as response:
            ready_id = json.load(response)["data"]["id"]
        self.assertTrue(run_once(account_id=account_id))
        self.assertEqual(self.call(first, f"/v1/memories/{ready_id}")[1]["data"]["status"], "ready")
        self.assertIn("Visible telescope text", self.call(first, f"/v1/memories/{ready_id}/content")[1]["data"]["body"])

    def test_docx_extraction_reprocess_and_import(self):
        first, csrf = self.register()
        second, other_csrf = self.register()
        account_id = self.started_accounts[-2]
        output = BytesIO()
        with ZipFile(output, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
            archive.writestr("word/document.xml", """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Orbital research memo</w:t></w:r></w:p><w:p><w:r><w:t>Second paragraph</w:t></w:r></w:p></w:body></w:document>""")
        docx = output.getvalue()
        invalid = Request(self.base + "/v1/uploads/docx?filename=bad.docx", data=b"not a zip",
                          method="POST", headers={"X-CSRF-Token": csrf})
        with self.assertRaises(HTTPError) as rejected:
            first.open(invalid, timeout=5)
        self.assertEqual(rejected.exception.code, 422)
        request = Request(self.base + "/v1/uploads/docx?filename=notes.docx", data=docx,
                          method="POST", headers={"X-CSRF-Token": csrf})
        with first.open(request, timeout=5) as response:
            memory_id = json.load(response)["data"]["id"]
        self.assertEqual(self.call(second, f"/v1/memories/{memory_id}/reprocess", "POST", csrf=other_csrf)[0], 404)
        self.assertTrue(run_once(account_id=account_id))
        content = self.call(first, f"/v1/memories/{memory_id}/content")[1]["data"]
        self.assertEqual(content["body"], "Orbital research memo\n\nSecond paragraph")
        self.assertEqual(content["version"], 1)
        self.assertEqual(self.call(first, "/v1/memories?q=Orbital&kind=document")[1]["data"]["total"], 1)
        with connection() as db:
            db.execute("UPDATE memories SET user_note = 'Keep this note' WHERE id = %s", (memory_id,))
        queued = self.call(first, f"/v1/memories/{memory_id}/reprocess", "POST", csrf=csrf)
        self.assertEqual(queued[0], 202)
        duplicate = self.call(first, f"/v1/memories/{memory_id}/reprocess", "POST", csrf=csrf)
        self.assertEqual(queued[1]["data"]["job_id"], duplicate[1]["data"]["job_id"])
        self.assertTrue(run_once(account_id=account_id))
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}/content")[1]["data"]["version"], 1)
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}")[1]["data"]["user_note"], "Keep this note")
        with first.open(self.base + "/v1/export", timeout=5) as response:
            exported = response.read()
        request = Request(self.base + "/v1/import?format=contextos", data=exported,
                          method="POST", headers={"X-CSRF-Token": other_csrf})
        with second.open(request, timeout=5) as response:
            report = json.load(response)["data"]
        self.assertEqual((report["imported"], report["failed"]), (1, 0), report)
        restored_id = report["items"][0]["memory_id"]
        self.assertEqual(self.call(second, f"/v1/memories/{restored_id}/content")[1]["data"]["body"], content["body"])
        with connection() as db:
            key = db.execute("SELECT object_key FROM memory_assets WHERE memory_id = %s", (memory_id,)).fetchone()["object_key"]
        path_for(key).write_bytes(b"damaged")
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}/reprocess", "POST", csrf=csrf)[0], 202)
        self.assertTrue(run_once(account_id=account_id))
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}")[1]["data"]["status"], "failed")
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}/content")[1]["data"]["body"], content["body"])

    def test_manual_url_capture_refresh_failure_and_export(self):
        first, csrf = self.register()
        second, other_csrf = self.register()
        account_id = self.started_accounts[-2]
        self.assertEqual(self.call(first, "/v1/urls", "POST", {"source_url": "http://127.0.0.1/private"}, csrf)[0], 422)
        self.assertEqual(self.call(first, "/v1/urls", "POST", {"source_url": "http://localhost/private"}, csrf)[0], 422)
        self.assertEqual(self.call(first, "/v1/urls", "POST", {"source_url": "https://example.com:8443/"}, csrf)[0], 422)
        with patch("backend.contextos.manual_urls.socket.getaddrinfo", return_value=[(2, 1, 0, "", ("10.0.0.5", 443))]):
            with self.assertRaises(ValueError):
                public_address("example.com", 443)
        self.assertEqual(checked_url("https://example.com/story")[1], "example.com")
        created = self.call(first, "/v1/urls", "POST", {"source_url": "https://example.com/story", "user_note": "Read later"}, csrf)
        self.assertEqual(created[0], 201)
        memory_id = created[1]["data"]["id"]
        self.assertEqual(self.call(second, f"/v1/memories/{memory_id}")[0], 404)
        page = {"title": "A useful story", "body": "Observatory findings", "author": "Ada",
                "image_uri": "https://example.com/photo.jpg", "published_at": None,
                "final_url": "https://example.com/story"}
        with patch("backend.contextos.manual_urls.fetch_page", return_value=page):
            self.assertTrue(run_once(account_id=account_id))
        detail = self.call(first, f"/v1/memories/{memory_id}")[1]["data"]
        self.assertEqual(detail["status"], "ready")
        self.assertEqual(detail["source_author"], "Ada")
        self.assertEqual(detail["capture_method"], "manual")
        self.assertEqual(self.call(first, "/v1/memories?q=Observatory")[1]["data"]["total"], 1)
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}/content")[1]["data"]["body"], "Observatory findings")
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}/reprocess", "POST", csrf=csrf)[0], 202)
        with patch("backend.contextos.manual_urls.fetch_page", side_effect=ValueError("http_403")):
            self.assertTrue(run_once(account_id=account_id))
        failed = self.call(first, f"/v1/memories/{memory_id}")[1]["data"]
        self.assertEqual((failed["status"], failed["capture_reason"], failed["user_note"]),
                         ("partial", "http_403", "Read later"))
        self.assertEqual(self.call(first, f"/v1/memories/{memory_id}/content")[1]["data"]["body"], "Observatory findings")
        with first.open(self.base + "/v1/export", timeout=5) as response:
            exported = response.read()
        request = Request(self.base + "/v1/import?format=contextos", data=exported,
                          method="POST", headers={"X-CSRF-Token": other_csrf})
        with second.open(request, timeout=5) as response:
            report = json.load(response)["data"]
        self.assertEqual((report["imported"], report["failed"]), (1, 0), report)
        restored = self.call(second, f"/v1/memories/{report['items'][0]['memory_id']}")[1]["data"]
        self.assertEqual((restored["capture_method"], restored["source_author"]), ("manual", "Ada"))

    def test_image_and_scanned_pdf_ocr(self):
        first, csrf = self.register()
        second, other_csrf = self.register()
        account_id = self.started_accounts[-2]
        image = Image.new("RGB", (900, 160), "white")
        ImageDraw.Draw(image).text((20, 20), "REMEMBER THE TELESCOPE", fill="black",
                                   font=ImageFont.truetype("arial.ttf", 48))
        image_bytes = BytesIO()
        image.save(image_bytes, format="PNG")
        request = Request(self.base + "/v1/uploads/image?filename=poster.png", data=image_bytes.getvalue(),
                          method="POST", headers={"X-CSRF-Token": csrf, "Content-Type": "image/png"})
        with first.open(request, timeout=5) as response:
            image_id = json.load(response)["data"]["id"]
        self.assertTrue(run_once(account_id=account_id))
        text = self.call(first, f"/v1/memories/{image_id}/content")[1]["data"]["body"]
        self.assertIn("TELESCOPE", text)
        self.assertEqual(self.call(first, f"/v1/memories/{image_id}")[1]["data"]["status"], "ready")
        for format_name, extension, mime in (("JPEG", "jpg", "image/jpeg"), ("WEBP", "webp", "image/webp")):
            variant = BytesIO()
            image.save(variant, format=format_name, quality=95)
            request = Request(self.base + f"/v1/uploads/image?filename=poster.{extension}", data=variant.getvalue(),
                              method="POST", headers={"X-CSRF-Token": csrf, "Content-Type": mime})
            with first.open(request, timeout=5) as response:
                variant_id = json.load(response)["data"]["id"]
            self.assertTrue(run_once(account_id=account_id))
            self.assertIn("TELESCOPE", self.call(first, f"/v1/memories/{variant_id}/content")[1]["data"]["body"])
        pdf_bytes = BytesIO()
        image.save(pdf_bytes, format="PDF")
        request = Request(self.base + "/v1/uploads/pdf?filename=scanned.pdf", data=pdf_bytes.getvalue(),
                          method="POST", headers={"X-CSRF-Token": csrf, "Content-Type": "application/pdf"})
        with first.open(request, timeout=5) as response:
            pdf_id = json.load(response)["data"]["id"]
        self.assertTrue(run_once(account_id=account_id))
        detail = self.call(first, f"/v1/memories/{pdf_id}")[1]["data"]
        self.assertEqual(detail["status"], "ready", detail)
        passage = self.call(first, f"/v1/memories/{pdf_id}/passages")[1]["data"]["items"][0]
        self.assertEqual(passage["page_number"], 1)
        self.assertIn("TELESCOPE", passage["body"])
        blank = BytesIO()
        Image.new("RGB", (200, 100), "white").save(blank, format="PNG")
        request = Request(self.base + "/v1/uploads/image?filename=blank.png", data=blank.getvalue(),
                          method="POST", headers={"X-CSRF-Token": csrf, "Content-Type": "image/png"})
        with first.open(request, timeout=5) as response:
            blank_id = json.load(response)["data"]["id"]
        self.assertTrue(run_once(account_id=account_id))
        self.assertEqual(self.call(first, f"/v1/memories/{blank_id}")[1]["data"]["status"], "partial")
        with first.open(self.base + "/v1/export", timeout=5) as response:
            exported = response.read()
        request = Request(self.base + "/v1/import?format=contextos", data=exported,
                          method="POST", headers={"X-CSRF-Token": other_csrf})
        with second.open(request, timeout=5) as response:
            report = json.load(response)["data"]
        self.assertEqual(report["failed"], 0, report)
        restored = {self.call(second, f"/v1/memories/{item['memory_id']}")[1]["data"]["title"]: item["memory_id"]
                    for item in report["items"]}
        self.assertIn("TELESCOPE", self.call(second, f"/v1/memories/{restored['poster']}/content")[1]["data"]["body"])
        self.assertIn("TELESCOPE", self.call(second, f"/v1/memories/{restored['scanned']}/passages")[1]["data"]["items"][0]["body"])
        with connection() as db:
            key = db.execute("SELECT object_key FROM memory_assets WHERE memory_id = %s", (image_id,)).fetchone()["object_key"]
        path_for(key).write_bytes(b"damaged")
        self.assertEqual(self.call(first, f"/v1/memories/{image_id}/reprocess", "POST", csrf=csrf)[0], 202)
        self.assertTrue(run_once(account_id=account_id))
        self.assertEqual(self.call(first, f"/v1/memories/{image_id}")[1]["data"]["status"], "failed")
        self.assertEqual(self.call(first, f"/v1/memories/{image_id}/content")[1]["data"]["body"], text)

    def test_manual_fetch_metadata_and_private_redirect(self):
        class Response:
            def __init__(self, status, body=b"", location=None):
                self.status, self.body, self.location = status, body, location

            def getheader(self, name, default=None):
                return {"Content-Type": "text/html; charset=utf-8", "Location": self.location}.get(name, default)

            def read1(self, size):
                chunk, self.body = self.body[:size], self.body[size:]
                return chunk

        class Connection:
            responses = []
            calls = []

            def __init__(self, host, port, ip, timeout):
                self.sock = None
                self.calls.append((host, port, ip))

            def request(self, method, target, headers):
                self.calls.append((method, target, headers["Host"]))

            def getresponse(self):
                return self.responses.pop(0)

            def close(self):
                pass

        html = (b'<html><head><title>Fallback</title><meta property="og:title" content="Primary title">'
                b'<meta name="author" content="Grace"><meta property="og:image" content="/cover.png">'
                b'<meta property="article:published_time" content="2025-02-03T00:00:00Z"></head>'
                b'<body><article><h1>Orbital news</h1><p>Readable page text</p></article>'
                b'<script>private form text</script></body></html>')
        Connection.responses = [Response(200, html)]
        with patch("backend.contextos.manual_urls.public_address", return_value="93.184.215.14"), \
             patch("backend.contextos.manual_urls.PinnedHTTPS", Connection):
            page = fetch_page("https://example.com/story")
        self.assertEqual(page["title"], "Primary title")
        self.assertEqual(page["author"], "Grace")
        self.assertEqual(page["image_uri"], "https://example.com/cover.png")
        self.assertEqual(page["published_at"].year, 2025)
        self.assertIn("Readable page text", page["body"])
        self.assertNotIn("private form text", page["body"])
        self.assertIn(("example.com", 443, "93.184.215.14"), Connection.calls)
        Connection.responses = [Response(302, location="http://127.0.0.1/private")]
        Connection.calls = []
        with patch("backend.contextos.manual_urls.public_address", return_value="93.184.215.14"), \
             patch("backend.contextos.manual_urls.PinnedHTTPS", Connection):
            with self.assertRaisesRegex(ValueError, "private_address"):
                fetch_page("https://example.com/redirect")
        self.assertEqual(len([item for item in Connection.calls if len(item) == 3 and item[0] == "example.com"]), 1)


if __name__ == "__main__":
    unittest.main()
