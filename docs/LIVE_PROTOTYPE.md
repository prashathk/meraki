# Live Meraki prototype

Deployed and verified on 17 October 2026.

- Public application: https://meraki-api-fgeq7eikua-ue.a.run.app/
- Source: https://github.com/prashathk/meraki
- Deployment project: `ai-builder-cup-511917`; region: `us-east1`.
- Scheduled shutdown: **14 November 2026, 09:00 Asia/Colombo**. The prototype is intentionally unavailable after shutdown; evaluation must finish before that deadline.

## Access

Create a student account and verify your email, then log in. University accounts require administrator verification before course preparation is available. Email/password authentication uses Firebase; Google sign-in is hidden until its provider is configured.

The project owner's administrator credentials are stored only in the private workstation `.env` as `CLOUD_ADMIN_EMAIL` and `CLOUD_ADMIN_PASSWORD`. Do not put these in the repository, public documents, issues or build arguments. The cloud database URL and Gemini key are in Secret Manager. Application and worker services use a service account, without downloaded service-account keys.

The initial catalogue contains six **clearly labelled fictional example courses**, matching a fresh local installation. Their example-domain course links are placeholders, not real admissions pages. The bundled historical ontology remains available through the administrator's migration/review workflow; it has not been implicitly published. Enquiries are delivered to the university workspace, not external email.

## Infrastructure and cost controls

The public Cloud Run API also serves the compiled frontend. Its worker requires Cloud Run IAM authentication and accepts only authenticated task invocations. Cloud SQL is the specifically designated **30-day PostgreSQL free trial**, confirmed by the console banner; it has not been upgraded. Private uploads and ontology snapshots use a non-public Cloud Storage bucket. Cloud Tasks provides durable extraction dispatch.

The existing `infra/main.tf` describes a normal paid production database and was **not applied** for this trial deployment. Do not run `terraform apply` against this project assuming it preserves the free-trial configuration.

Both services use request-based billing, zero minimum instances, one CPU and 2 GiB memory. The API allows at most two instances; the worker allows one. The application image is approximately 268 MB compressed, and only one image version was retained at initial deployment. These controls target the services' free usage allowances; they are not a hard spending cap. Network traffic, excessive usage and supporting services can still cause charges. Do not upgrade the SQL trial or enable billing on the separate Gemini Developer API Free Tier project without reviewing the consequences.

Two shutdown mechanisms are configured:

1. A desktop scheduled task in this chat runs on **14 November at 09:00 Asia/Colombo** and verifies shutdown. It requires the computer, desktop app and cloud credentials to be available.
2. Four Google Cloud Tasks are scheduled for **14 November at 09:05 Asia/Colombo**, independently of the workstation. They pause `meraki-extraction`, request the SQL instance's `activationPolicy=NEVER`, and remove the `meraki-api` and `meraki-worker` Cloud Run services. They do not delete the database or private stored files. Task API acceptance does not itself prove the final shutdown state; check the operation results and instance/service state.

These tasks use the dedicated `meraki-shutdown` service account and a custom role containing only SQL instance get/update, task queue pause, and Cloud Run service get/delete permissions. A read-only task successfully reached the SQL API using the same OAuth transport. The local private deployment inventory is `data/cloud-deployment-state.json`; credentials are never included in it.

Google's SQL trial does not automatically become paid: an explicit upgrade is required. Trial limitations include no normal backups or SLA. Do not create a chargeable final backup as part of shutdown without separate authorization. Stopping a normal paid SQL instance does not eliminate storage/IP costs; inspect any resources left after shutdown.

## Verification

The deployed environment passed checks for:

- Firebase sign-in, administrator/student/university roles, organization verification and access denials.
- Public catalogue/taxonomy, recommendations, saved courses, private history and PDF export.
- ClamAV rejection of the standard antivirus test sample and acceptance of a benign text upload.
- Private GCS uploads and real Cloud Tasks worker delivery.
- NLP extraction and Gemini Developer API extraction, each producing three drafts from the bundled sample document.
- Representative review/submission, administrator approval/publication, and restoration of the previous catalogue version.
- Anonymous denial of access to the worker.
- Responsive public layout at 320, 768 and 1440 pixels, plus both light and dark themes.

Temporary Firebase test identities and disposable test records/objects were removed after verification. Local checks also passed: 38 backend tests and the frontend production build.

ClamAV signatures are baked into the image at build time; rebuild with updated signatures before extending the prototype beyond its planned trial. Production document uploads fail closed when scanning is unavailable. Gemini uses the configured free-tier model allowlist and reports quota/access failures rather than falling back to a paid model; upstream quota availability cannot be guaranteed.

## Scoring update — 18 October 2026

Student recommendations now support per-tag percentage scores and configurable contributions under `degree-category-score-coverage-v2`. The calculation uses each degree's complete unique category counts, with the same ranking in SQL before limiting results. Profile settings, calculation details and policy text are preserved in private history and PDFs; earlier recommendation snapshots retain their original results and policy. See [the scoring contract](RECOMMENDATION_SCORING.md).

Verification passed: 87 backend tests, the frontend build, desktop/mobile light/dark checks, PDF rendering, 18 comparisons on live PostgreSQL, and live API checks for weights, profile persistence, snapshots and unchanged legacy history/PDF text. The release was tested at a preview revision before public traffic switched. No database schema migration or user-data rewrite was needed. The scheduled shutdown date remains unchanged.
