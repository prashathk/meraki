# Meraki deployment handover

Start here. Prepared 17 October 2026 for CAPS Innovation: Ayantha Fernando, Prashath Kandasamy and Charith Perera.

**Deployment update:** a Cloud Run prototype is now live. See [LIVE_PROTOTYPE.md](docs/LIVE_PROTOTYPE.md) for the verified URL, access instructions, current limitations and scheduled shutdown. The original packaging checks below describe the handover state before this deployment.

## What is delivered

React/TypeScript frontend with Midnight Focus dark/light themes; FastAPI API; extraction worker; SQLAlchemy/Alembic persistence; original ontology; admin review/publication; dependency lockfiles; tests; container, Firebase Hosting, Cloud Build and Terraform configuration.

This is a functional local MVP for staging/pilot deployment. Google Cloud resources have not been provisioned or live-tested. See `docs/IMPLEMENTATION_CHECKLIST.md` and `docs/VERIFICATION.md` for known limits. No cloud credentials or private application database are included.

## 1. Verify and extract the release

Verify the ZIP against its adjacent SHA256 file before extraction. On Windows use `Get-FileHash <archive.zip> -Algorithm SHA256`; on Linux use `sha256sum <archive.zip>`. Extract to a normal writable directory and run all commands from its `Meraki` directory. `MANIFEST.json` lists individual payload file sizes and SHA256 hashes.

## 2. Local Windows setup

Install Python **3.13** and Node.js **22** (including npm), available on PATH. Edge is needed only for the supplied browser tests.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1
```

The script creates `.venv`, installs locked dependencies, builds the frontend and copies `.env.example` only if `.env` does not exist. It preserves existing configuration and data. Do not run this development setup with production environment variables exported. For this local setup the code's defaults match `.env.example`; editing `.env` alone does not export variables to every process.

Open two terminals in the extracted root:

```powershell
# Terminal 1: API and built frontend
.\.venv\Scripts\python.exe -m uvicorn backend.meraki.app:app --host 127.0.0.1 --port 8000
```

```powershell
# Terminal 2: extraction worker
.\.venv\Scripts\python.exe -m worker.run
```

Open http://127.0.0.1:8000/. API docs: http://127.0.0.1:8000/api/docs. Stop each terminal with Ctrl+C. The optional hidden-process launcher is for convenience; interactive terminals are recommended for handover.

## 3. Linux/macOS setup

Python 3.13 with venv support and Node.js 22 must be available. In the extracted root:

```bash
bash scripts/setup.sh
# Terminal 1
.venv/bin/python -m uvicorn backend.meraki.app:app --host 127.0.0.1 --port 8000
# Terminal 2, in the same extracted root
.venv/bin/python -m worker.run
```

Use `PYTHON=/path/to/python3.13 bash scripts/setup.sh` if needed. Linux/macOS setup commands are provided; the handover extraction test was performed on Windows, not those operating systems.

## 4. Accounts and ontology data

Fresh development startup creates six illustrative courses and these local accounts, all with password `DEMO_PASSWORD` from your private local `.env`: `student@meraki.local`, `university@meraki.local`, `admin@meraki.local`. These are development-only identities.

To recreate the original ontology catalogue while the local API is running:

```powershell
.\.venv\Scripts\python.exe -m scripts.migrate_prototype --apply
```

On Linux use `.venv/bin/python` instead. This development-only runner creates a consistent SQLite backup, previews/stages the bundled ontology, records structural approval through admin APIs, archives only illustrative seed courses and publishes 211 historical offerings. It tests recovery/reactivation. It will not approve unrelated submissions. Without `--apply` it previews only. Alternatively use admin **Prototype migration**, then review and publish through the UI.

Expected counts: Kelaniya 105, Moratuwa 20, Sri Jayewardenepura 86; 201 degree concepts, 20 university/faculty associations, 207 original taxonomy terms. Shared degree concepts are resolved from reciprocal graph restrictions. These are historical records, with current admissions/availability and tags not independently verified. Public URLs may be explicitly labelled university catalogue/homepage fallbacks. See `docs/LEGACY_MIGRATION_REPORT.md`.

The ZIP deliberately excludes the current workstation's SQLite database, sessions, enquiries, logs, uploads, private snapshots and backups. Re-import the bundled ontology; do not copy development identities/session tables into production. Production import uses a real Firebase administrator and the same preview/stage/review/publish UI; the demo-account CLI refuses production mode.

## 5. Verify a local installation

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe scripts/verify-release.py --base-url http://127.0.0.1:8000
node scripts/verify_theme_browser.mjs
# After original ontology migration:
node scripts/verify_legacy_browser.mjs
```

The standalone browser checks require installed Edge, frontend dependencies and the API on port 8000. The broader `npm run test:e2e` in `frontend` additionally expects Vite on port 5173 (`npm run dev`) and the worker running. Tests intentionally create local fixture activity/drafts. Backend tests use isolated temporary databases. Use test accounts/data in staging.

## 6. Docker alternative

With Docker Engine and Compose available, `docker compose up --build` starts PostgreSQL, API and worker at http://127.0.0.1:8080/. API and worker share the private-data volume. `docker compose down` stops services while preserving volumes; do not add `-v` unless intentionally discarding all local data. Compose credentials are local-only. This container workflow has not been executed in the handover environment because Docker Engine was unavailable.

The SQLite-only migration runner is for the default Python development setup. For Docker/PostgreSQL use the admin migration UI, with review/publication as usual.

## 7. Google Cloud staging release

Follow `docs/GOOGLE_CLOUD_STEP_BY_STEP.md` in order. It includes Cloud Shell commands, project/IAM setup, Terraform, Cloud SQL, private storage, secrets, build arguments, Firebase, migration jobs, administrator bootstrap, deployment and checks. `docs/DEPLOYMENT.md` covers operational controls. Replace every placeholder with reviewed environment values. Provisioning/deployment is an operator action with billing implications; packaging does not execute it.

Required production decisions/configuration:

- Google project/region, Firebase project and canonical hosting origin.
- `APP_ENV=production`, `AUTH_PROVIDER=firebase`, Cloud SQL `DATABASE_URL` supplied via Secret Manager.
- Service identities with least-privilege access to SQL/storage/tasks; Application Default Credentials, no checked-in keys.
- Private `STORAGE_BUCKET`, Cloud Tasks queue, worker URL and task invoker identity.
- Public frontend `VITE_FIREBASE_CONFIG` at build time; rebuild for the target project. Included `frontend/dist` is a convenience development build with no production Firebase configuration.
- Explicit Alembic migration and verified Firebase admin bootstrap before opening traffic.
- Optional Gemini/Vertex model/project configuration; extraction must report missing credentials instead of simulating results.

Cloud Build is build-only. Terraform configuration is infrastructure preparation, not proof of deployment. Do not treat a successful image build as a successful release.

## 8. Release acceptance and rollback

In staging verify Firebase login/role enforcement, university verification, multiple-course extraction and evidence review, source/custom URLs, admin partial approval/publication, student filtering/matches/PDF, consented enquiries/activity attribution, Cloud Tasks retry behavior, private object access, and dark/light mobile controls. Check logs for failed tasks and database errors.

Run `python scripts/verify-release.py --base-url https://YOUR_HOST --production` for a read-only HTTP/auth-mode smoke check. It does not replace the role/workflow checks above. Do not enable document upload until the scanner executable/signatures are provisioned and tested; the current image does not bundle them. OCR and a trained production NER corpus/model are not supplied. Complete the documented administrator MFA client flow and other release gates before broad production release.

Before upgrades, record the serving Cloud Run revision/image digest, active ontology version and database backup/PITR status. Use a staging database to validate schema migrations first. Roll traffic back to the previous compatible Cloud Run revision for a code release failure. Restore an ontology version through admin UI for a catalogue issue. Database rollback requires a reviewed restore procedure and schema compatibility; do not blindly downgrade or overwrite the database while writers run. Source data, private object storage and database backups must be retained together as required by the operational retention policy.

See `docs/HANDOVER_VERIFICATION.md` for extracted-release verification and its limits.

## Package map

| Path | Purpose |
|---|---|
| `backend/`, `worker/` | API, migration, ontology and worker code |
| `frontend/` | Source, lockfile, logo, tests, development build, Hosting config |
| `backend/fixtures/prototype-ontology.owl` | Portable original ontology for reviewed migration |
| `scripts/setup.ps1`, `scripts/setup.sh` | Fresh-machine development setup |
| `scripts/verify-release.py` | Read-only running-release HTTP smoke check |
| `scripts/bootstrap_admin.py` | Explicit production administrator initialization |
| `infra/`, `Dockerfile`, `cloudbuild.yaml` | Google infrastructure and image build |
| `docs/` | Deployment, verification, migration, scope and sample input |
| `.env.example`, `frontend/.env.example` | Configuration examples, not real secrets |
| `MANIFEST.json` | Checksums for all packaged payload files |

Historical reports refer to evidence/backups on the development workstation. These private/generated folders are excluded; use the supplied scripts to generate fresh evidence on the target machine. No third-party dataset/institutional permissions or brand ownership rights are granted by this archive; confirm authorized use before public launch.
