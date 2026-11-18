"""Separate durable extraction worker entry point."""

import logging
import time

from .jobs import claim_one, finish
from .extract_text import PermanentExtractionError, handle as extract_text
from .extract_pdf import handle as extract_pdf
from .extract_docx import handle as extract_docx
from .object_cleanup import cleanup_one

log = logging.getLogger(__name__)

HANDLERS = {"extract_text": extract_text, "extract_pdf": extract_pdf, "extract_docx": extract_docx}


def run_once(account_id=None) -> bool:
    job = claim_one(account_id=account_id)
    if job is None:
        return cleanup_one(account_id=account_id)
    handler = HANDLERS.get(job["job_type"])
    if handler is None:
        finish(job["id"], job["account_id"], job["attempt_count"],
               error_code="unsupported_job_type", permanent=True)
        log.error("Unsupported job type %s", job["job_type"])
        return True
    try:
        handler(job)
    except PermanentExtractionError as exc:
        log.warning("Job %s failed with %s", job["id"], exc.code)
        finish(job["id"], job["account_id"], job["attempt_count"],
               error_code=exc.code, permanent=True)
    except Exception:
        log.exception("Job %s failed", job["id"])
        finish(job["id"], job["account_id"], job["attempt_count"],
               error_code="processor_failed")
    else:
        finish(job["id"], job["account_id"], job["attempt_count"])
    return True


def main():
    logging.basicConfig(level=logging.INFO)
    while True:
        if not run_once():
            time.sleep(2)


if __name__ == "__main__":
    main()
