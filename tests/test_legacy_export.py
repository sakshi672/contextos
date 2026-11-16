"""Confirm the local prototype can be snapshotted without losing records."""

import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from zipfile import ZipFile

from backend.contextos.legacy_export import export_legacy


class LegacyExportTest(unittest.TestCase):
    def test_snapshot_preserves_records_and_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "context.db"
            output = root / "snapshot.zip"
            with closing(sqlite3.connect(source)) as db:
                db.execute("""CREATE TABLE memories (
                    id text PRIMARY KEY, title text, kind text, source_url text,
                    note text, captured_at text, updated_at text)""")
                db.execute("INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?)", (
                    "memory-1", "Research", "link", "https://example.com/one",
                    "A note with Unicode: क", "2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00",
                ))
                db.execute("INSERT INTO memories VALUES (?, ?, ?, ?, ?, ?, ?)", (
                    "memory-2", "Thought", "note", "", "Second note",
                    "2026-01-03T00:00:00+00:00", "2026-01-03T00:00:00+00:00",
                ))
                db.commit()
            before = hashlib.sha256(source.read_bytes()).hexdigest()

            self.assertEqual(export_legacy(source, output), 2)
            with ZipFile(output) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                content = archive.read("memories.jsonl")
                records = [json.loads(line) for line in content.splitlines()]
            self.assertEqual(manifest["memory_count"], 2)
            self.assertEqual(manifest["memories_sha256"], hashlib.sha256(content).hexdigest())
            self.assertEqual([record["id"] for record in records], ["memory-1", "memory-2"])
            self.assertEqual(records[0]["note"], "A note with Unicode: क")
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
            with self.assertRaises(FileExistsError):
                export_legacy(source, output)


if __name__ == "__main__":
    unittest.main()
