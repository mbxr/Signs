# Build report — v1.1 (November 1, 2026)

## Verified in the ChatGPT development runtime

- `python -m compileall -q app tests`: passed.
- `node --check static/app.js`: passed.
- `pytest -q`: **13 passed**.
  - Login and CSRF protection
  - Batch upload, duplicate detection and deterministic stub-OCR-to-Excel integration
  - Template field validation and calibration gate
  - Image format checking
  - Successful synthetic geometric alignment preflight
  - Fail-closed alignment when features are unavailable
  - Failed OCR manual-entry path and audit history
  - Field validators, retry path and spreadsheet formula injection prevention
  - Accuracy benchmark arithmetic
  - Additive migration from original v1 SQLite template schema
- Standalone Uvicorn HTTP request to `/api/health`: HTTP 200.
- Project packaging excludes data, customer photographs, caches and `.env` secrets.

## Not verified — do not infer these tests passed

- Production Docker build (Docker not available locally).
- Real PaddleOCR inference/model download/CPU performance on Ubuntu KVM 2 (PaddlePaddle not installed here).
- Real handwritten form OCR accuracy; no meaningful accuracy percentage available.
- Full graphical browser smoke test (headless Chromium stalled in this execution environment).
- Public HTTPS configuration, deployed server security, scheduled backup/restore and processing a 1,000-image batch.

**What to do next:** deploy a private test instance, test model download and CPU inference, calibrate a reference form, use alignment preflight, process a small photo pilot, manually verify results, then benchmark via `docs/OCR_EVALUATION.md`. Avoid production bulk import before evaluating the pilot.
