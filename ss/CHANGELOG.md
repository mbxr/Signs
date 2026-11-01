# Changelog

## v1.1 — November 1, 2026

- Requires explicit reference-form calibration before accepting order uploads.
- Stops OCR rather than misassigning fields when template alignment fails.
- Adds alignment preflight via the Form template page.
- Enables full manual data entry after failed OCR.
- Tracks field corrections and shows history in the review screen.
- Exports Original OCR and Review queue Excel worksheets in addition to Orders.
- Adds local ground-truth accuracy benchmark and CSV template.
- Adds constrained schema upgrade for installations that used the first ZIP.
- Rejects file extensions that disagree with decoded image format.
- Adds optional offline worker networking configuration after model caching.
- Extends local automated tests from 6 to 13 passing tests.

## v1.0 — initial codebase

- User login, uploads, SQLite queue, PaddleOCR adapter, template editing, review dashboard, Excel and Docker scaffold.
