# RetailIQ Backend

RetailIQ is the Flask backend for the RetailIQ retail operating system. This repository is aligned to the current verified frontend contracts and the workspace parity source of truth.

## Current Verified Status

- Backend route mapping is closed
- Backend `ruff format --check .` passed
- Backend `ruff check app tests` passed
- Backend `pytest -q` passed
- Backend `pip_audit` passed for `requirements.txt` and `requirements-core.txt`
- Live smoke checks against the deployed backend passed for `/health`, `/`, `/api/v1/ops/maintenance`, and `/api/v1/team/ping`

## Source Of Truth

The canonical parity artifacts live in the workspace folder:

- `D:/Files/Desktop/Retailiq-Frnt-Bknd-Shortcuts/parity-source-of-truth.md`
- `D:/Files/Desktop/Retailiq-Frnt-Bknd-Shortcuts/parity-summary.json`
- `D:/Files/Desktop/Retailiq-Frnt-Bknd-Shortcuts/backend-to-frontend-matrix.csv`
- `D:/Files/Desktop/Retailiq-Frnt-Bknd-Shortcuts/frontend-to-backend-matrix.csv`

## Runtime Notes

- Auth uses merchant/staff JWT flows under `/api/v1/*`
- Dashboard collections use named-key envelopes
- The backend is task-driven for async work such as OCR, analytics snapshots, forecasting, and notifications
- The deployed backend URL is the production integration target for the frontend

## Notes

- Keep backend contracts aligned with the parity source of truth.
- Do not reintroduce mock dashboard data or stale audit claims into this README.
