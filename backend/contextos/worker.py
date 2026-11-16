"""Separate worker entry point. Extraction handlers are added with uploads."""

import logging
import time

from .jobs import claim_one, finish

log = logging.getLogger(__name__)

# The queue and lease are ready; no extraction job is enqueued until a handler
# ships with its corresponding capture route.
HANDLERS = {}


def run_once() -> bool:
    job = claim_one()
    if job is None:
        return False
    handler = HANDLERS.get(job["job_type"])
    if handler is None:
        finish(job["id"], job["account_id"], error_code="unsupported_job_type", retry_seconds=3600)
        log.error("Unsupported job type %s", job["job_type"])
        return True
    try:
        handler(job)
    except Exception:
        log.exception("Job %s failed", job["id"])
        finish(job["id"], job["account_id"], error_code="processor_failed")
    else:
        finish(job["id"], job["account_id"])
    return True


def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        if not run_once():
            time.sleep(2)


if __name__ == "__main__":
    main()
