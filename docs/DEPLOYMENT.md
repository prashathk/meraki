# Google Cloud deployment runbook

No infrastructure was provisioned. Prepare a reviewed plan before any billable action.

For the first deployment, follow [the detailed 16-step Google Cloud guide](GOOGLE_CLOUD_STEP_BY_STEP.md). It includes Cloud Shell commands, foundation/image bootstrapping, Firebase setup and the administrator verification sequence. This file is the shorter operations summary.

## Prerequisites and release gates

1. A Google Cloud/Firebase project, billing authorization, a supported Gemini model and region, and reviewed residency requirements.
2. A verified Firebase administrator identity, email/Google sign-in providers enabled and approved authorized frontend domains. Apply an admin MFA policy before public release.
3. Production PostgreSQL migration test, current dependency/security review and parser/malware scanning setup. The default production upload gate rejects unscanned documents.
4. Protect Terraform state: database bootstrap password is sensitive but still stored in state. Use encrypted restricted remote state; populate Secret Manager separately. Do not commit `terraform.tfvars` or generated state.

## Sequence

- Review `infra/main.tf`; enable APIs/create Artifact Registry through a reviewed bootstrap plan before building the first image. Infrastructure creation and image deployment are separate stages because the registry must exist before push.
- Create/populate the existing Secret Manager secret named by `database_secret_id` with a SQLAlchemy URL, for example `postgresql+psycopg://meraki:URL_ENCODED_PASSWORD@/meraki?host=/cloudsql/PROJECT:REGION:INSTANCE`. Restrict access to the runtime service account. Do not log the value.
- Build the Docker image with `VITE_FIREBASE_CONFIG` set to the public Firebase web configuration. `cloudbuild.yaml` builds/pushes an immutable image; it does not deploy automatically.
- Review a Terraform plan using a concrete image URI. Resources include private storage, Cloud SQL with backups/PITR, queue, private worker and API service.
- Run `alembic upgrade head` as a controlled one-off job with database access. Initialize the empty published version and verified admin using `python -m scripts.bootstrap_admin --uid ... --email ... --name ...`. This command requires privileged Firebase credentials; never expose it through the API.
- Complete migration/bootstrap before inviting users. Services may be provisioned earlier during staged setup so the first Firebase account can be verified; database-dependent paths are not ready until initialization finishes. Set production Firebase identity, CORS, database, storage and task variables. API is publicly reachable but protected data endpoints verify Firebase identity/roles. Catalogue/taxonomy/health are intentionally public.
- Cloud Run worker **must not** grant `allUsers` invoke permission. Only the task dispatch identity receives invoker permission. Never expose `worker.api` on a public local network or public unauthenticated service: it relies on the platform IAM boundary.
- Either use the SPA included in the API image or deploy `frontend/dist` to Firebase Hosting with the supplied rewrites. Update region/service names in `frontend/firebase.json` if changed.
- Schedule `scripts.dispatch_pending` with the same runtime environment to redeliver queued jobs after dispatch errors and reclaim jobs with expired 15-minute leases. Schedule retention with an explicitly reviewed policy. Commands are supplied; scheduler resources are not provisioned yet.

## Smoke checks

Verify `/api/health` reports Firebase/production; local `/api/auth/login` and `/api/auth/register` are unavailable. Verify cross-user report denial and tenant isolation. Demonstrate verified membership, extraction, public course URL review, approval, publication, recommendation, enquiry and rollback using non-sensitive pilot data. Confirm signed task OIDC invocation and access denial to an unauthenticated worker call. Verify Gemini billing and evidence-backed multi-course output using real permissions.

## Recovery

- Ontology rollback reactivates a verified prior version and writes an audit event. It does not undo enquiries or user activity and does not replace database backups.
- Cloud SQL backups/PITR recover the database through a separate reviewed restore operation. Test recovery to a new instance before switching traffic.
- Objects/snapshots are versioned in the private bucket. Retain snapshot checksum/manifests and align retention policies with database references.
- For failed extraction, inspect state/error without logging document contents; correct input/configuration and retry. Cancellation invalidates the worker claim. A stale worker must not commit after another claim takes ownership.
- Restore an older application image only with compatible schema. Destructive automatic migration downgrade is intentionally disabled.

## Cost controls

Compute API/worker instance caps, database pools and queue rates are bounded. Add organization quotas and model spend monitoring before growth. Budget alerts are notifications, not a hard spending limit. Quote costs only after checking current official regional pricing against actual source/token/page traffic. Database baseline can dominate a low-traffic pilot.

## Official implementation references

- https://firebase.google.com/docs/auth/admin/verify-id-tokens
- https://fastapi.tiangolo.com/tutorial/security/
- https://ai.google.dev/gemini-api/docs/structured-output
- https://cloud.google.com/run/docs
- https://cloud.google.com/tasks/docs/creating-http-target-tasks
- https://cloud.google.com/sql/docs/postgres/backup-recovery/backups
