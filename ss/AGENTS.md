# Project guidance for coding assistants

- FastAPI backend in `app/main.py`; SQLAlchemy models in `app/db.py`; worker in `app/worker.py`.
- Vanilla JS browser interface in `static/` (no JS build step). Keep all interactions first-party and accessible.
- Uploaded photos, crops, model weights, exports and SQLite files live only in `data/` and must never enter Git.
- No hosted AI inference: `app/ocr.py` integrates local PaddleOCR 3.x.
- Field names are defined in `app/template.py`. Keep them stable for exports.
- Every form has one Order and one Job. Existing human-verified fields must not be overwritten by worker retries.
- Tests must run with an isolated temporary DATA_DIR. Do not use actual customer images in tests.
- Preserve original OCR text, human-corrected values, warnings and review flags separately.
- Prevent spreadsheet formula injection; preserve string data as literals in Excel cells.
- All editing requests must enforce session authorization and CSRF.
- Read `IMPLEMENTATION_STATUS.md` and `docs/DEPLOYMENT.md` before changing infrastructure.
- No automatic production update until a deployment has been manually verified.
