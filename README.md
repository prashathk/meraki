# Meraki

**Find Your Path. Follow Your Passion.**

**Live prototype:** https://meraki-api-fgeq7eikua-ue.a.run.app/ — scheduled to shut down on **14 November 2026 at 09:00 Asia/Colombo**. See [deployment, access and verification details](docs/LIVE_PROTOTYPE.md).

Education and course discovery by **CAPS Innovation** - Ayantha Fernando, Prashath Kandasamy and Charith Perera.

A functional local implementation of the approved Meraki frontend direction and core prototype workflows. Students receive private explained recommendations; verified university teams extract multiple degree courses from documents/URLs and review them as a list; administrators approve revisions and activate/recover ontology versions.

**Status:** functional prototype deployed to Cloud Run with Firebase authentication, a Cloud SQL trial and private storage. It is not a certified production release. See [the implementation checklist](docs/IMPLEMENTATION_CHECKLIST.md) for remaining master-prompt scope and release gates. Fresh demo seed records are fictional; the bundled original ontology can be migrated as labelled historical university offerings.

For a portable deployment release, start with [HANDOVER.md](HANDOVER.md). It covers fresh-machine setup, data import, verification, Google Cloud release and rollback.

## Start locally on Windows

Prerequisites: Python 3.13 and Node.js 22. Dependencies are installed by the setup commands below.

From the repository root, for a fresh setup:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.lock.txt
.\.venv\Scripts\python.exe -m scripts.configure_local
cd frontend
npm ci
npm run build
cd ..
```

Start the API/combined built frontend in one terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.meraki.app:app --host 127.0.0.1 --port 8000
```

Start the durable local extraction worker in another terminal:

```powershell
.\.venv\Scripts\python.exe -m worker.run
```

Open **http://127.0.0.1:8000/**. API documentation: **http://127.0.0.1:8000/api/docs**.

For frontend development/hot reload, run `npm run dev` in `frontend` and open **http://127.0.0.1:5173/**. Vite proxies `/api` to port 8000. Run commands from the documented directory; database/storage paths are relative to the repository root. Do not start a duplicate server if the port is already in use.

An optional `scripts/start-local.ps1` starts hidden API/worker processes and logs under `data/`; it expects dependencies installed and a frontend build. Interactive terminals are easier to stop during development.

### Private local configuration

The repository contains no shared demo password or live API key. `python -m scripts.configure_local` generates private local credentials in the Git-ignored `.env`. API keys, databases, uploads, logs, generated screenshots/builds and Terraform state are excluded from Git. Before publishing changes, run `python -m scripts.audit_publication` against staged files; `--ref HEAD` verifies a committed tree.

### Demo accounts

| Role | Email | Password source |
|---|---|---|
| Student | `student@meraki.local` | `DEMO_PASSWORD` from your private local `.env` |
| University representative | `university@meraki.local` | `DEMO_PASSWORD` from your private local `.env` |
| Administrator | `admin@meraki.local` | `DEMO_PASSWORD` from your private local `.env` |

The development banner is intentional. Registration is local-only and does not pretend to verify email. Development identity is rejected at startup when `APP_ENV=production`. The production adapter uses Firebase ID-token verification plus authoritative application roles/membership. No actual email is sent for local enquiries: they are stored in the university inbox.

### Try the complete workflow

1. Log in as a student; generate a recommendation, compare/save courses and download a PDF.
2. Log in as the university team. Upload `docs/sample-prospectus.txt` or use your own text-bearing PDF/DOCX. Choose NLP baseline to run without cloud credentials.
3. Wait for the worker to create three draft degree rows. Open **Edit details** for each. Review tags and faculty, then choose **Use source URL** or **Use a different URL**. Document-only sources require a public course URL before submission.
4. Save each reviewed draft. Select the rows and submit the batch.
5. Log in as the administrator. Select a submitted row, inspect evidence, enter a reason and approve. Request changes on another row to demonstrate partial approval.
6. Open **Ontology versions** and publish approved revisions. Only approved courses enter the active catalogue. Previous versions remain recoverable with an audit reason.
7. Return as a student, generate a new run and view the approved course. **Explore course** uses its chosen student-facing public link. Submit a consented enquiry and inspect it in the university workspace.
8. View admin analytics and audit history. Demo `.example` links are intentionally fictional; add a real authorized course source/URL when testing external navigation.

## Features

- Role-aware home, sign-up/login, pending institutional verification and server-side authorization.
- Navy/blue Meraki identity, responsive desktop/mobile layouts and text-only degree cards.
- Degree/university/faculty search, taxonomy filters, combined matching, green matched tags, saved courses, comparison and PDF snapshots.
- Multi-course source extraction, a persistent worker queue, evidence-backed editable list, source/custom public URL per course and selected batch submission.
- Frozen submissions, per-row decisions, new revisions, SHACL-validated RDF snapshots, optimistic version activation and audited recovery; taxonomy additions and course retirement.
- Missed-course entry, per-source list filtering, refresh/cancellation, application-account deletion/redaction and explicit retention cleanup.
- Search, course-view, explore and enquiry activities; university-scoped inbox and aggregate analytics.
- Expiring local sessions, hashed passwords, private reports, guarded URL fetches, durable task state, upload limits and production scan gate.

## Recommendation policy

Candidates come from indexed course-tag relationships in the active published version. Queries bind taxonomy IDs; users cannot submit arbitrary SPARQL/SQL. Each stable CourseOffering appears once.

`score = 100 * (0.70 * selected-interest coverage + 0.30 * selected-aptitude coverage)`

Coverage is the fraction of selected tags matched by the course in that preference family. If only one family is provided, its weight is 1. Empty/unknown IDs produce a controlled validation response. Ties use title and stable course ID. The frontend labels the value **preference match**, not a probability of success. All demo eligibility is unknown. AI-suggested aptitudes are suitability metadata, not official admission requirements.

Recommendation runs persist the score policy, active version, selected tags and result snapshot. PDF exports use that historical snapshot rather than recalculating against current data.

## Extraction modes

- **Local lexical baseline:** runnable rules detect degree headings and associate the latest faculty heading. It is deliberately labelled as a baseline, not a trained NER model. The supplied sample is formatted for this path.
- **spaCy trained model:** install `backend/requirements-ner.txt`, prepare permissioned labelled JSONL and run `python -m scripts.train_ner dataset.jsonl`. Configure `NER_MODEL_PATH`. Use `scripts/evaluate_ner.py` against institution-held-out data before claiming production quality. No production corpus/model has been supplied or trained here.
- **Gemini:** the local default uses the Gemini Developer API with a server-side `GEMINI_API_KEY` from a Google AI Studio **Free Tier** project and `GEMINI_MODEL=gemini-3.5-flash-lite`. Only the reviewed free-tier model IDs are allowed; the project must remain on Free Tier to avoid charges. See [local Gemini setup](docs/GEMINI_LOCAL_SETUP.md). The adapter validates verbatim evidence and approved tags; quota failures do not switch models or providers. The legacy Vertex route requires explicit `GEMINI_PROVIDER=vertex`, Cloud project/model settings and Application Default Credentials.
- Scans/OCR have a clear unsupported state until a real OCR provider is configured. Production file upload additionally requires `CLAMSCAN_PATH`; the image currently does not bundle a scanner/database, so provision one before enabling document uploads in production.

Example labelled JSONL entry for training format (illustrative, not sufficient training data):

```json
{"text":"BSc Computer Science","entities":[[0,20,"DEGREE_TITLE"]]}
```

## Configuration and persistence

Copy `.env.example` as needed. Uvicorn can load it with `--env-file .env`; separate CLI commands need the same environment exported. Never commit secrets. Run `python -m scripts.configure_local` to create private local demo credentials in `.env` before a fresh startup.

- Default database: `data/meraki.db` (SQLite).
- Production database: `DATABASE_URL=postgresql+psycopg://...` to Cloud SQL.
- Private source/snapshot objects: `data/objects` locally; `STORAGE_BUCKET` switches to Cloud Storage.
- `APP_ENV=production`, `AUTH_PROVIDER=firebase` are required in cloud.
- Frontend Firebase config is build-time `VITE_FIREBASE_CONFIG` JSON. Web config is public configuration; service credentials are never embedded.
- `TASKS_QUEUE`, `WORKER_URL`, `TASKS_SERVICE_ACCOUNT` enable Cloud Tasks dispatch.
- Cloud API/worker use service identity, not downloaded keys in source files.

`records` stores typed domain aggregates with indexed owner/org/state columns. Dedicated `course_tags` and `version_courses` tables provide indexed graph traversal and immutable publication membership. This is a practical MVP schema, with further normalization documented as production work. Published course revisions are frozen. Recommendation snapshots reference stable versions. Source provenance and public course URLs are separate fields.

Alembic migration:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

Development seeds/create-table behavior is convenient for a fresh demo. Production migrations/bootstrap should run explicitly before enabling traffic. Do not run production schema changes through public endpoints. PostgreSQL integration is not claimed verified until its test environment is available.

Docker alternative: `docker compose up --build` starts PostgreSQL, API/frontend and worker. Docker Desktop's engine must be running. Compose reads private `POSTGRES_PASSWORD` and `DEMO_PASSWORD` values from `.env`; no credentials are embedded in the compose file. No Docker containers were created during the initial build because the engine was unavailable.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
cd frontend
npm run build
npm run test:e2e
```

Browser tests use installed Microsoft Edge and expect API, worker and Vite running on ports 8000/5173. They exercise all three roles and write preview screenshots to `output/`. API tests use an isolated temporary database. A recommendation PDF is rendered and its text/content checked. These tests are not a penetration test or a claimed pilot impact result.

See `docs/VERIFICATION.md` for the most recent verification record. Lockfiles pin the installed Python/npm dependency set. Rebuild/retest after changing dependencies.

## Deployment and operations

Read [the Google Cloud runbook](docs/DEPLOYMENT.md) before provisioning. Dockerfile serves the SPA and API in one image; Firebase Hosting can alternatively host the frontend and proxy `/api` to Cloud Run. Cloud Build is intentionally **build-only**. Terraform describes infrastructure, but no cloud resources have been created and no billable deployment was performed.

For a first deployment, use the [16-step Google Cloud deployment guide](docs/GOOGLE_CLOUD_STEP_BY_STEP.md), including reviewed Cloud Shell commands, Firebase configuration, migration jobs, administrator bootstrap and release checks.

Useful source files:

- `backend/meraki/app.py`: typed routes and authorization.
- `backend/meraki/domain.py`: scoring, graph snapshot and publication.
- `backend/meraki/extraction.py`: bounded fetch/parsing and model adapters.
- `worker/run.py`: durable local jobs; `worker/api.py`: private cloud worker.
- `frontend/src/main.tsx`: role-based application screens.
- `scripts/import_legacy.py`: dry-run legacy ontology audit.
- `scripts/retention.py`: dry-run retention cleanup; `--apply` deletes eligible expired events/session/rate rows.

## Known release limitations

Live cloud providers, production NER, OCR/scanning infrastructure, advanced eligibility filters, source refresh scheduling, taxonomy editing/retirement, external identity-deletion verification, broader accessibility/security review and deployed target-load benchmarks still require work or external setup. A synthetic local benchmark is documented separately; it is not a production capacity claim. The original ontology has been structurally migrated into the local catalogue; historical availability and institutional endorsement are not independently verified. Institutional outreach, measured satisfaction claims and public deployment are not implied. The detailed checklist records scope rather than hiding these limitations.


## Original ontology migration

The current local database contains 211 historical offerings from the original ontology. Fresh development databases still start with six illustrative courses. Admins can use **Prototype migration** to preview/upload `backend/fixtures/prototype-ontology.owl`, stage resolved offerings, review submissions and publish an ontology version. The preview does not change the active catalogue.

For the bundled fixture in local development only, `python -m scripts.migrate_prototype --apply` backs up SQLite and runs the same review/publication APIs, retiring only illustrative seed offerings. Without `--apply` it previews. Do not use the demo-identity runner in production. See [migration report](docs/LEGACY_MIGRATION_REPORT.md) for counts, provenance and recovery.
