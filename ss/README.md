# Surprise Signs — Private Order Form Digitizer

A self-hosted web application for turning standardized photographs of handwritten Surprise Signs order forms into searchable records and downloadable Excel workbooks. **No hosted AI inference.**

## Features

- Password-protected dashboard and private JPG/PNG/WebP upload endpoints
- Batch upload with SHA-256 duplicate detection
- Persistent SQLite processing jobs; one OCR worker by default
- PaddleOCR 3.x local CPU OCR integration in the Docker worker
- Mandatory template calibration, normalized field regions, drag-to-calibrate canvas and alignment preflight
- OpenCV ORB feature matching to align new photos to the reference
- Fail-closed alignment detection; manual entry for failed images; correction audit trail
- Searchable order table, status filters, and batch filters
- `.xlsx` export (Orders, Original OCR, Review queue) for all orders, batches, or reviewed orders
- Local ground-truth benchmark: `python -m app.benchmark /data/ground_truth.csv`
- Configurable security via environment variables and private Docker network

## Important limitations before bulk processing

This is a **functional first-version codebase**, not yet a proven production deployment. Tests can validate the API and Excel logic, but the actual PaddleOCR engine must be run on Ubuntu and measured against sample handwriting. The initial template rectangles are ESTIMATES based on one photograph. The API blocks batch upload until a reference image has been uploaded and its field regions explicitly saved. An alignment failure now aborts OCR rather than risking cross-field mistakes; failed orders can be manually entered. OCR output and checkbox estimates are subject to mistakes. Never trust customer email addresses or dates without review.

The worker requires internet access once to download AI model weights; actual document inference is local thereafter. Keep the images and `.env` private. Real photos are NOT included in this repository.

## Ubuntu deployment

**Start here:** [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md). Verify the actual Ubuntu version and existing services on ports 80/443 before deployment.

## Local development without OCR

The API and UI can run independently of the OCR model, but uploads won't be processed unless the worker is running with PaddleOCR installed.

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
export DATA_DIR="$(pwd)/data"
python -m app.cli init-db
python -m app.cli create-admin admin
uvicorn app.main:app --reload
```

Open http://localhost:8000. For testing, run `pytest -q` (no customer photos required). To run OCR locally on Linux CPU, install PaddlePaddle/PaddleOCR according to the Dockerfile and start `python -m app.worker` in another terminal.

## Workflows

1. Deploy and create an administrator via CLI.
2. Sign in, visit **Form template**, upload a reference photo, adjust all 13 regions and save calibration.
3. Click **Test photo alignment** and use another representative photograph.
4. Upload a 30–50-photo pilot, check any failed alignments, and inspect crops and extracted text.
5. Correct OCR values, verify fields and mark orders reviewed; failures support manual transcription.
6. Download Excel with separate original-OCR and review-queue worksheets.
7. Measure local accuracy with `docs/OCR_EVALUATION.md` before bulk import.

## Data paths

`data/uploads` originals; `data/crops` ROI previews; `data/templates` reference photographs; `data/orders.sqlite3` database; `data/models` local OCR weights. The whole `data` directory is ignored by Git.

## Security reminders

Single private administrator is the intended deployment profile. A login is required for data endpoints, edit requests require CSRF protection, passwords use salted scrypt hashes, and uploads are type/size-validated. Use HTTPS with Caddy, a private GitHub repository, a strong administrator password, and off-site encrypted backups. Do not allow untrusted users to operate the deployment without further security review.

## Evidence and technical references

PaddleOCR's official 3.x API and local installation: https://www.paddleocr.ai/main/en/quick_start.html and https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/paddlepaddle_installation.en.md . The docker worker is intended to use CPU inference; actual performance is unverified.

## Upgrading from the first ZIP

Back up your `data/` directory before deploying this release. On startup, a narrow additive SQLite migration adds the template `calibrated` flag where missing and creates the field-correction audit table. Existing calibration must be reviewed and re-saved before accepting more photographs. Future database schema changes will require formal migrations.
