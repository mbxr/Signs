# Implementation status — hardened v1.1

## Implemented and tested locally

- Private login, cookie session, CSRF checks, upload validation and SHA-256 duplicate detection.
- SQLite orders, batches, OCR fields, persistent jobs and field-correction audit history.
- Mandatory reference upload + explicit field-region calibration before batch importing.
- Lightweight alignment preflight endpoint and UI test action (no order created by preflight).
- Fail-closed image alignment: OCR is skipped if document registration is unsuccessful or spatially inconsistent.
- Local PaddleOCR adapter (intended for Docker worker; **not actually run in this environment**).
- Single-job-at-a-time worker, restart recovery, failed-job retry and manual transcription when OCR fails.
- Authenticated review UI with original image, individual crops, corrections, verification and correction-history view.
- Excel exporter: `Orders`, `Original OCR`, `Review queue`, `Read me` tabs, with formula injection protection.
- Privacy-preserving ground-truth OCR benchmark, producing aggregate accuracy rates from local CSV data.
- Narrow additive migration for the original v1 SQLite database: `templates.calibrated` column, default `False`. Audit table created on initialization.
- Ubuntu Docker Compose + Caddy scaffold and optional network-isolated worker override after model download.
- CI/test suite: 13 tests pass locally, including synthetic alignment preflight and v1 database upgrade test.

## Not verified — important before real customer usage

- PaddlePaddle/PaddleOCR installation and real handwriting inference inside Ubuntu Docker.
- OCR accuracy/throughput/RAM usage on Hostinger KVM 2 hardware.
- Docker image build or Compose runtime (Docker unavailable in this development environment).
- Live HTTPS/TLS, access control, backups/restores and other services already present on VPS.
- Real-browser interaction testing (Chromium did not complete in this execution environment).
- Large upload batches / interruption behavior on the deployed host.

## Future engineering tasks

- Replace narrow additive schema upgrade with a general Alembic migration system.
- Benchmark 30–50 representative forms and calibrate image registration thresholds.
- Improve checkbox detection (currently conservative heuristic, always needs review).
- Configure a secure domain or VPN behind the user's existing VPS services.
- Perform a targeted security assessment and rehearsal of backup restoration before production use.

Real customer images and example customer personal information are **not** included in this package.
