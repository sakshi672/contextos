# Phase 4 keyword retrieval baseline

Run `.venv\Scripts\python.exe evaluation\keyword_baseline.py` from the repository root with the local PostgreSQL database running. The runner creates an isolated temporary schema, seeds the six synthetic memories in `seed_cases.json`, runs the app's PostgreSQL search function, writes `keyword_baseline_results.json`, and removes the schema.

The result records each expected item's rank and automated query-to-identification time. It is a development baseline, not a human time-to-find study. The corpus uses titles and notes, including a PDF and image record, but does not contain real extracted PDF/OCR text. Integration tests separately cover active extracted content, PDF page matches, edit/reindexing, deletion, and account isolation.

The partial-word fallback is labeled in the UI when no all-words result exists. This is still keyword matching; semantic interpretation and observed user retrieval tasks remain part of Phase 6 and public-readiness evaluation.
