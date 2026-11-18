"""Run the Phase 0 synthetic corpus against the real PostgreSQL search query.

Usage: .venv/Scripts/python.exe evaluation/keyword_baseline.py
"""

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg import sql

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from backend.contextos.database import connection
from backend.contextos.local_db import load_env
from backend.contextos.migrate import migrate
from backend.contextos.search import search_memories


def main() -> None:
    load_env()
    database_url = os.environ["CONTEXT_OS_DATABASE_URL"]
    schema = f"contextos_eval_{uuid.uuid4().hex}"
    previous_options = os.environ.get("PGOPTIONS")
    corpus = json.loads((HERE / "seed_cases.json").read_text(encoding="utf-8"))
    try:
        with psycopg.connect(database_url) as db:
            db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        os.environ["PGOPTIONS"] = f"-c search_path={schema}"
        migrate()
        account_id = uuid.uuid4()
        ids = {}
        with connection() as db:
            db.execute("INSERT INTO accounts (id, email, password_hash) VALUES (%s, %s, %s)",
                       (account_id, "eval@example.test", "synthetic-evaluation-only"))
            for item in corpus["items"]:
                memory_id = uuid.uuid4()
                ids[str(memory_id)] = item["id"]
                source = item["source"] if item["source"] and item["source"].startswith("https://") else None
                db.execute("""INSERT INTO memories (id, account_id, kind, title, source_uri, captured_at,
                    status, user_note) VALUES (%s, %s, %s, %s, %s, %s, 'ready', %s)""",
                    (memory_id, account_id, item["kind"], item["title"], source,
                     datetime.fromisoformat(item["saved_at"]).replace(tzinfo=timezone.utc), item["note"]))

        cases = []
        for query in corpus["queries"]:
            start = time.perf_counter()
            response = search_memories(
                q=query["query"], session={"account_id": account_id}, kind="all", domain=None,
                date_from=None, date_to=None, project_id=None, tag_id=None, collection_id=None,
                limit=100, offset=0,
            )["data"]
            found = [ids[str(row["id"])] for row in response["items"]]
            rank = found.index(query["expected_id"]) + 1 if query["expected_id"] in found else None
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            cases.append({"query": query["query"], "clue_type": query["clue_type"],
                          "expected_id": query["expected_id"], "rank": rank,
                          "time_to_find_ms": elapsed_ms if rank is not None else None,
                          "query_ms": elapsed_ms, "result_count": response["total"]})
        report = {"corpus": "seed_cases.json", "engine": "PostgreSQL keyword search",
                  "sample_size": len(cases), "top_1": sum(case["rank"] == 1 for case in cases),
                  "cases": cases,
                  "note": "Synthetic metadata-only baseline. Time to find is automated query-to-identification in API results, including a local database connection; it is not human UI task-completion time."}
        output = HERE / "keyword_baseline_results.json"
        output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Top-1: {report['top_1']}/{report['sample_size']}; wrote {output}")
    finally:
        if previous_options is None:
            os.environ.pop("PGOPTIONS", None)
        else:
            os.environ["PGOPTIONS"] = previous_options
        if schema.startswith("contextos_eval_") and len(schema) == len("contextos_eval_") + 32:
            with psycopg.connect(database_url) as db:
                db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    main()
