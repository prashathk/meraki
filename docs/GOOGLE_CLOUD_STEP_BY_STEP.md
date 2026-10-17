# Meraki: step-by-step Google Cloud deployment guide

Prepared 17 October 2026 for the application in this repository.

## Can the application be deployed?

**Yes.** The repository contains a container build, cloud-provider adapters, database migration, Terraform infrastructure and Firebase Hosting configuration. The recommended first deployment is a **staging/pilot environment**.

Local application tests and Terraform schema validation have passed. The image has **not** been built/run on Google Cloud, PostgreSQL/cloud integrations have not been verified live, and no cloud resources have been provisioned. Follow the checks below before declaring a deployment successful.

The current image does not include malware-scanner binaries/signatures or OCR. Production mode rejects unscanned document uploads. You can initially validate public HTML URL ingestion; complete step 15 before advertising document upload/OCR. Mandatory administrator MFA also requires completing/testing the client challenge flow, not just enabling a console switch.

## Deployment layout

| Component | Google service | What it does |
|---|---|---|
| React frontend | Firebase Hosting | Serves static assets and forwards `/api/**` to Cloud Run |
| FastAPI backend | Cloud Run: `meraki-api` | User workflows, recommendations, reports and approval APIs |
| Extraction worker | Private Cloud Run: `meraki-worker` | Runs source parsing and NLP/Gemini extraction |
| Durable data | Cloud SQL for PostgreSQL | Accounts, course revisions, graph edges, versions and activity |
| Private files | Cloud Storage | Sources and immutable ontology snapshots |
| Identity | Firebase Authentication | Email/password and Google identity; application DB controls roles |
| AI | Gemini on Vertex AI | Optional schema-constrained extraction and tag suggestions |
| Background dispatch | Cloud Tasks | Authenticated worker invocation with retries |
| Images/builds | Artifact Registry + Cloud Build | Builds and stores the application container |
| Configuration | Secret Manager | Database connection secret |

The Docker image also contains the compiled frontend, so Cloud Run can serve the whole app directly. This guide uses Firebase Hosting as the canonical browser URL, matching `frontend/firebase.json`. The worker must remain private. [Cloud Run deployment documentation](https://docs.cloud.google.com/run/docs/deploying), [Firebase Hosting / Cloud Run integration](https://firebase.google.com/docs/hosting/cloud-run).

## 1. Prepare accounts, permissions and tools

You need:

- A Google Cloud project with billing enabled and authorization to provision paid services.
- Permission to enable APIs, create service accounts/IAM bindings, build images, create Cloud SQL/storage/queues, manage secrets and deploy services/jobs.
- Firebase access to the **same** project.
- A private source repository containing this application's source, or a source upload to Cloud Shell.
- Google Cloud Shell with Git, Node.js, Python and Terraform. Run `terraform version` and install a supported Terraform CLI if absent. Do not upload the Windows Terraform executable from `tmp/` to Cloud Shell.

**All terminal commands below use Bash in Google Cloud Shell**, not PowerShell. Open Cloud Shell from the Google Cloud console. Replace placeholders before running commands. Commands are supplied for you to review; none have been executed against your cloud account.

Before provisioning, create a billing budget and alerts. Cloud SQL has ongoing baseline costs even when Cloud Run has no requests. Alerts do not automatically cap spending. Size the pilot using current regional pricing; no monthly cost estimate is implied here.

## 2. Put the source in Cloud Shell

Recommended: push reviewed source to your private Git repository, then clone it in Cloud Shell:

```bash
git clone YOUR_PRIVATE_REPOSITORY_URL meraki
cd meraki
```

The local project is currently at:

```text
PATH_TO_YOUR_MERAKI_CHECKOUT
```

If you prepare the first Git commit on Windows, add the source folders explicitly and review the staged diff before pushing. Include `frontend/public/meraki-logo.png`, lockfiles, migrations and cloud configuration. Do not commit `.env`, credentials, database files, Terraform variable/state files or local generated reports.

Alternatively upload source through Cloud Shell Editor. Include:

```text
backend/ frontend/ worker/ scripts/ infra/ docs/
Dockerfile .dockerignore .gcloudignore .gitignore
alembic.ini cloudbuild.yaml compose.yaml README.md
```

Exclude `.venv`, `node_modules`, `data`, `output`, `tmp`, `.terraform`, secrets and local `.env` files. The supplied `.gcloudignore` also excludes these from Cloud Build source uploads.

Checkpoint: `ls Dockerfile backend/requirements.lock.txt frontend/package-lock.json infra/main.tf` succeeds.

## 3. Choose a project and deployment settings

Use a new staging project if possible. Add Firebase to that existing project rather than accidentally creating a second project. [Firebase: use an existing Google Cloud project](https://firebase.google.com/docs/projects/use-firebase-with-existing-cloud-project).

```bash
export PROJECT_ID="YOUR_PROJECT_ID"
export REGION="us-central1"
export REPOSITORY="meraki"
export DB_SECRET="meraki-database-url"
export APP_SA="meraki-app@${PROJECT_ID}.iam.gserviceaccount.com"
export TASK_SA="meraki-task-dispatch@${PROJECT_ID}.iam.gserviceaccount.com"
export STATE_BUCKET="${PROJECT_ID}-meraki-tfstate"

gcloud config set project "$PROJECT_ID"
gcloud auth list
```

This example uses `us-central1` because the checked-in Firebase rewrite uses that region. If choosing another supported region, update **all** service/model/queue settings and `frontend/firebase.json`. Confirm Gemini model availability and residency/latency needs before provisioning. Do not assume every model is available in every region.

Enable APIs and create the empty database secret container:

```bash
gcloud services enable \
  run.googleapis.com sqladmin.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com cloudtasks.googleapis.com aiplatform.googleapis.com \
  identitytoolkit.googleapis.com cloudbuild.googleapis.com storage.googleapis.com

gcloud secrets create "$DB_SECRET" --replication-policy=automatic
```

For an existing deployment, inspect/reuse the existing secret instead of recreating it. Do not overwrite production credentials while following a staging walkthrough.

## 4. Configure Firebase Authentication

In the Firebase console:

1. Open/add Firebase to `$PROJECT_ID`.
2. Register a **Web app**, named `Meraki Web`.
3. In Authentication, enable **Email/Password** and optionally **Google**. Complete the Google provider support-email configuration.
4. Review authentication email templates and authorized domains.
5. Ensure `$PROJECT_ID.web.app` is authorized. Add a custom domain later when configured. Add the Cloud Run hostname only if you intentionally use its hosted frontend for browser sign-in too.
6. Copy the public Firebase Web configuration.

Store the config in a Cloud Shell file named `firebase-web-config.json`, for example:

```json
{
  "apiKey": "YOUR_FIREBASE_WEB_API_KEY",
  "authDomain": "YOUR_PROJECT_ID.firebaseapp.com",
  "projectId": "YOUR_PROJECT_ID",
  "storageBucket": "COPY_THE_ACTUAL_VALUE_FROM_FIREBASE",
  "messagingSenderId": "YOUR_SENDER_ID",
  "appId": "YOUR_WEB_APP_ID"
}
```

This web configuration is public client configuration, **not a service-account key**. Copy the actual values, especially the storage bucket name; do not infer them from this example. Never put private service-account credentials into this file or a `VITE_*` variable.

```bash
export FIREBASE_CONFIG="$(python3 -c 'import json; print(json.dumps(json.load(open("firebase-web-config.json")), separators=(",", ":")))')"
```

Keep this operator configuration outside commits. The build must receive it **before** compiling the frontend; setting a Cloud Run environment variable afterward will not update the compiled React bundle.

## 5. Initialize Terraform state and variables

Create a private, access-restricted state bucket with versioning. State can contain database credentials, even when Terraform marks an input sensitive.

```bash
gcloud storage buckets create "gs://${STATE_BUCKET}" \
  --location="$REGION" --uniform-bucket-level-access
gcloud storage buckets update "gs://${STATE_BUCKET}" \
  --public-access-prevention --versioning

cat > infra/backend.tf <<'EOF'
terraform {
  backend "gcs" {}
}
EOF
```

Restrict state-bucket IAM to deployment operators. Use a separate state prefix/project for production. If an approved remote backend already exists, use that instead.

```bash
export TF_VAR_project_id="$PROJECT_ID"
export TF_VAR_region="$REGION"
export TF_VAR_database_secret_id="$DB_SECRET"
export TF_VAR_web_origin="https://${PROJECT_ID}.web.app"
export TF_VAR_gemini_model="YOUR_SUPPORTED_GEMINI_MODEL_ID"
export TF_VAR_image="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/meraki:bootstrap-placeholder"

read -r -s -p "Choose a strong database password: " TF_VAR_database_user_password
echo
export TF_VAR_database_user_password

terraform -chdir=infra init \
  -backend-config="bucket=${STATE_BUCKET}" \
  -backend-config="prefix=meraki/staging"
terraform -chdir=infra validate
```

The placeholder image is used only while creating foundation resources. Do not deploy a service with that value. Retain the database password in an approved password manager; future Terraform operations need the same intended secret value. Do not enable shell tracing (`set -x`) around secrets.

## 6. Provision foundation resources first

The image repository and SQL instance must exist before the first image build and database connection secret. For this initial bootstrap only, use a reviewed targeted plan:

```bash
terraform -chdir=infra plan -out=foundation.tfplan \
  -target=google_project_service.api \
  -target=google_artifact_registry_repository.images \
  -target=google_service_account.app \
  -target=google_service_account.task \
  -target=google_project_iam_member.app_roles \
  -target=google_service_account_iam_member.dispatch_as_task \
  -target=google_secret_manager_secret_iam_member.database \
  -target=google_storage_bucket_iam_member.objects \
  -target=google_sql_user.app \
  -target=google_sql_database.db \
  -target=google_cloud_tasks_queue.extract

terraform -chdir=infra show foundation.tfplan
terraform -chdir=infra apply foundation.tfplan
```

Review costs, IAM and names before the apply command. This creates paid resources. Targeting is a bootstrap exception; use a full plan in step 9 and for normal updates.

Checkpoint: Artifact Registry contains the `meraki` repository; Cloud SQL contains `meraki-postgres` with database/user `meraki`; private storage, runtime accounts and extraction queue exist. SQL provisioning can take several minutes.

## 7. Store the database connection secret

```bash
export SQL_CONNECTION="$(gcloud sql instances describe meraki-postgres --format='value(connectionName)')"
export DB_URL="$(python3 - <<'PY'
import os
from urllib.parse import quote
password = quote(os.environ['TF_VAR_database_user_password'], safe='')
connection = os.environ['SQL_CONNECTION']
print(f'postgresql+psycopg://meraki:{password}@/meraki?host=/cloudsql/{connection}')
PY
)"

printf '%s' "$DB_URL" | gcloud secrets versions add "$DB_SECRET" --data-file=-
unset DB_URL
```

Record the newly created secret version number. The example below uses `1` for migration/bootstrap jobs; replace it if your version differs. Terraform services currently bind `latest`, so review secret rotation together with service revision rollout.

No application code should print this value. Cloud Run connects through the mounted `/cloudsql/PROJECT:REGION:INSTANCE` socket; the runtime account needs Cloud SQL Client access. [Cloud Run to PostgreSQL connection guidance](https://docs.cloud.google.com/sql/docs/postgres/connect-run).

## 8. Build the container with the correct Firebase config

First determine the project's actual build identity. Projects do not all use the same default Cloud Build account:

```bash
gcloud builds get-default-service-account --region="$REGION"
```

Ensure the returned build identity can write images to this Artifact Registry repository and write build logs/read its source-staging bucket. Scope grants to the relevant resources where possible. Do not grant the application's runtime account broad build/editor permissions. [Default Cloud Build account behavior](https://docs.cloud.google.com/build/docs/cloud-build-service-account-updates).

Submit the build:

```bash
export BUILD_ID="$(gcloud builds submit . \
  --region="$REGION" \
  --config=cloudbuild.yaml \
  --substitutions="^|^_REGION=${REGION}|_REPOSITORY=${REPOSITORY}|_FIREBASE_CONFIG=${FIREBASE_CONFIG}" \
  --async --format='value(id)')"

gcloud builds log "$BUILD_ID" --region="$REGION" --stream
gcloud builds describe "$BUILD_ID" --region="$REGION" --format='value(status)'
```

The alternate `|` substitution delimiter prevents commas inside Firebase JSON from becoming separate substitutions. Do not include `|` characters in the config values with this example.

Proceed only after status is **SUCCESS**:

```bash
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/meraki:${BUILD_ID}"
export TF_VAR_image="$IMAGE"
```

For stricter release immutability, copy the built image's digest from Artifact Registry and use its `.../meraki@sha256:...` URI as `IMAGE` and `TF_VAR_image`. Do not reuse a mutable `latest` tag for releases.

If the first Linux build fails, fix and rebuild before continuing. Local Windows installation/build success is not evidence that the container image succeeded.

## 9. Deploy the API and private worker

```bash
terraform -chdir=infra plan -out=services.tfplan
terraform -chdir=infra show services.tfplan
terraform -chdir=infra apply services.tfplan

export API_URL="$(terraform -chdir=infra output -raw api_url)"
export WORKER_URL="$(terraform -chdir=infra output -raw worker_url)"
```

Inspect the resulting service configuration:

| Setting | API | Worker |
|---|---|---|
| Identity | `meraki-app` runtime account | `meraki-app` runtime account |
| Environment | `APP_ENV=production`, `AUTH_PROVIDER=firebase` | Same |
| Database | Secret Manager `DATABASE_URL` + SQL mount | Same |
| Objects | Private `STORAGE_BUCKET` | Same |
| Task settings | Queue path, worker URL, dispatch account | N/A |
| Gemini | Extraction happens in worker | Project, location, model ID |
| Public invocation | API is reachable; protected routes verify Firebase | **Not allowed** |

The template grants public reachability to the API, including its static home page, but not privileged API access. At this point the environment is still under setup: database-dependent paths may fail until step 10/12. Do not invite users or call it a live production release yet.

Check IAM: the worker's invoker should be `$TASK_SA`, never `allUsers`. Cloud Tasks uses a signed OIDC token, and the API runtime account needs permission to act as that dispatch identity. [Authenticated Cloud Tasks requests](https://docs.cloud.google.com/tasks/docs/creating-http-target-tasks).

## 10. Run database migrations as a one-off job

Use the same built image and the restricted application account:

```bash
gcloud run jobs create meraki-migrate \
  --region="$REGION" --image="$IMAGE" \
  --service-account="$APP_SA" \
  --set-cloudsql-instances="$SQL_CONNECTION" \
  --set-env-vars="APP_ENV=production,AUTH_PROVIDER=firebase" \
  --set-secrets="DATABASE_URL=${DB_SECRET}:1" \
  --command=python --args=-m,alembic,upgrade,head \
  --max-retries=0 --task-timeout=600s

gcloud run jobs execute meraki-migrate --region="$REGION" --wait
```

Use `jobs update` rather than `create` when the job already exists. Confirm the execution succeeded; inspect sanitized job logs if not. This creates the schema, not demonstration users or a real course catalogue. Production startup intentionally does not seed local accounts. [Cloud Run Jobs command reference](https://docs.cloud.google.com/sdk/gcloud/reference/run/jobs/create).

## 11. Publish the frontend to Firebase Hosting

From the repository root in Cloud Shell:

```bash
cd frontend
npm ci
VITE_FIREBASE_CONFIG="$FIREBASE_CONFIG" npm run build
npx firebase-tools login --no-localhost
npx firebase-tools deploy --only hosting --project "$PROJECT_ID"
cd ..
```

Review the `firebase-tools` package/version before installation under your team's dependency policy. If already authenticated, reuse that session. The Hosting rewrite must reference service `meraki-api` in `$REGION`; modify the checked-in `us-central1` value if you chose another region.

Open `https://PROJECT_ID.web.app`. Check the home page and sign-up page. The local development banner must be absent. API `/api/health` should report `production` and `firebase`. Its Gemini flag currently reflects the API process's variables; extraction configuration lives in the worker, so validate Gemini there through a real job rather than relying on that flag alone.

## 12. Bootstrap the first administrator carefully

The bootstrap script requires a **verified Firebase user that does not already have an application DB account**.

1. Use a dedicated administrator email you control.
2. On the deployed Meraki sign-up page, create the Firebase account. In production, the client sends verification and stops before application onboarding when email is unverified.
3. Open the verification email and verify the address.
4. **Do not log into Meraki yet.** A normal first login would onboard the account as a student/representative, and the bootstrap script deliberately refuses to overwrite an existing account.
5. Copy that verified user's UID from Firebase Authentication and set:

```bash
export ADMIN_UID="VERIFIED_FIREBASE_USER_UID"
export ADMIN_EMAIL="YOUR_ADMIN_EMAIL"
export BOOTSTRAP_SA="meraki-bootstrap@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts create meraki-bootstrap \
  --display-name="Meraki one-time administrator bootstrap"
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${BOOTSTRAP_SA}" --role=roles/cloudsql.client
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${BOOTSTRAP_SA}" --role=roles/firebaseauth.admin
gcloud secrets add-iam-policy-binding "$DB_SECRET" \
  --member="serviceAccount:${BOOTSTRAP_SA}" --role=roles/secretmanager.secretAccessor

gcloud run jobs create meraki-bootstrap-admin \
  --region="$REGION" --image="$IMAGE" \
  --service-account="$BOOTSTRAP_SA" \
  --set-cloudsql-instances="$SQL_CONNECTION" \
  --set-env-vars="APP_ENV=production,AUTH_PROVIDER=firebase,GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
  --set-secrets="DATABASE_URL=${DB_SECRET}:1" \
  --command=python \
  --args="-m,scripts.bootstrap_admin,--uid,${ADMIN_UID},--email,${ADMIN_EMAIL},--name,Meraki Administrator" \
  --max-retries=0

gcloud run jobs execute meraki-bootstrap-admin --region="$REGION" --wait
```

The deployment operator needs permission to act as this bootstrap account. Do not grant Firebase Authentication Admin to the normal API/worker account just to make this job work.

Successful bootstrap creates the admin application account, default taxonomy and an empty active ontology, and sets the Firebase role claim. Now sign into Meraki normally; routing uses the account's actual role rather than the login role selector. Verify the administrator dashboard appears.

Remove the bootstrap account's elevated Firebase/secret access after success and lock down/delete the one-off bootstrap job under your operational policy. If it reports an existing application account, stop and use a reviewed privilege-change procedure or a fresh dedicated admin identity; do not delete arbitrary DB rows.

## 13. Test the real end-to-end journey

Use non-sensitive pilot data and authorized university sources:

1. Register and verify a student. Confirm private profile/history access.
2. Register a university representative. Confirm course preparation is denied while membership is pending.
3. As admin, verify the institution and representative after independent checks.
4. As the representative, supply an authorized public **HTML** course-listing URL. Choose NLP baseline or the configured Gemini mode.
5. Confirm the source becomes queued/running/completed and multiple courses appear as editable rows. A single empty/failed source must not alter existing published data.
6. Review each course's title, faculty, inferred tags and evidence. Set the same source URL or a different public details URL per course.
7. Submit selected rows. Confirm they remain absent from student discovery before approval/publication.
8. Approve one row, request changes on another, then publish approved revisions. Check only the approved offering is discoverable.
9. Generate student recommendations; inspect matching green tags, score reasons and the approved Explore course URL. Save, compare and download a PDF.
10. Submit a consented course enquiry. Confirm it appears only in the correct institution's workspace and is counted separately from contact intent.
11. Restore the previous ontology version and verify catalogue membership and audit history.
12. Test a different user/institution token: it must not retrieve someone else's PDF, profile, draft or enquiry.
13. An unauthenticated request to the worker must be rejected by Cloud Run IAM.

Cloud authentication, Cloud SQL behavior, model output and worker OIDC invocation are **not validated** merely because Terraform and the image build succeeded. Record actual smoke-test evidence.

## 14. Configure maintenance and monitoring

Create separate Cloud Run Jobs using the same image/runtime account/SQL secret:

- `python -m scripts.dispatch_pending`: set `TASKS_QUEUE`, `WORKER_URL` and `TASKS_SERVICE_ACCOUNT`; re-dispatches queued jobs and reclaims expired 15-minute leases. Run approximately every five minutes after testing.
- `python -m scripts.retention`: dry-run first; use `--apply` only after reviewing the 90-day event/session/rate cleanup policy. Run on a reviewed schedule.

Use Cloud Scheduler with an appropriate job-execution identity to trigger the jobs; grant only the required invocation permission. Scheduler resources are not included in the present Terraform file, so provision them through your team's infrastructure workflow and record ownership.

Configure Monitoring alerts for API/worker errors and latency, Cloud Tasks backlog/oldest age, SQL connection/storage pressure, failed jobs and unexpected model spend. Avoid recording student profiles or document contents in logs. Enable and verify SQL backups/PITR and exercise a restore into a separate test instance.

## 15. Complete public-launch prerequisites

Before opening the full service publicly:

- **Document scanning:** the current scanner adapter calls a configured local executable through `CLAMSCAN_PATH`. The supplied Dockerfile does not install that executable or signatures. Build and test an updated image with maintained scanning capability and adequate resources, or implement an authenticated scanning-service adapter. Scan both uploaded and fetched PDF/DOCX files. Do not bypass the gate by enabling development mode in cloud.
- **OCR:** implement/configure an OCR provider for scans, with limits and evidence retention. Current scanned documents intentionally fail with an actionable message.
- **Admin MFA:** finish/test Firebase multi-factor challenge handling and the production enforcement policy. The current login UI does not complete a mandatory MFA challenge; enabling it blindly can prevent administrator sign-in.
- **Model quality:** train/evaluate the domain NER with permissioned data or validate Gemini extraction on held-out university sources. The lexical baseline is not a production-trained model.
- **Data:** approve genuine course sources, public links and affiliation mappings. Do not migrate local demo credentials or assume the legacy audit is a verified production catalogue.
- **Release checks:** PostgreSQL integration, concurrency/publication, penetration testing, accessibility and deployed load tests; privacy/consent/retention policy and operational ownership.
- **Cost:** review model quotas, worker/API caps, SQL sizing, budget alerts and recovery costs.

The current local 10k-course performance result is a synthetic SQLite/TestClient benchmark, not a Google Cloud capacity measurement. The implementation checklist tracks remaining scope.

## 16. Updates, rollback and troubleshooting

### Update procedure

1. Run local tests and review schema changes.
2. Build a new image with a new build ID/digest; rebuild Hosting assets if frontend changes.
3. Back up data and apply compatible migrations through the one-off migration job.
4. Update `TF_VAR_image`, review a **full** Terraform plan, apply and run smoke tests.
5. Publish the matching Hosting assets; record image digest, API revision, migration revision and ontology version.

### Rollback

- For an application regression, direct traffic to a verified previous Cloud Run revision with `gcloud run services update-traffic`, then reconcile the desired image/traffic in infrastructure configuration. Hosting assets must remain API-compatible.
- For incorrect course data, use the admin's audited ontology restore action; do not roll back the whole database unnecessarily.
- For database loss, follow Cloud SQL backup/PITR recovery into a verified instance before switching connections. An older application image does not undo migrations.
- Do not run `terraform destroy` as a routine rollback. SQL and services have deletion protection; storage/state must be retained according to policy.

### Common issues

| Symptom | Check / resolution |
|---|---|
| `auth/invalid-api-key` or blank Firebase configuration | Web config was missing at build time. Correct it and rebuild image/Hosting assets. |
| `auth/unauthorized-domain` | Add the actual browser frontend hostname in Firebase authorized domains; review Google provider configuration. |
| Login needs email verification | Follow the verification email. Production intentionally refuses unverified identities. |
| Administrator bootstrap says account exists | Normal onboarding already happened; use a reviewed elevation path or a fresh dedicated admin identity. |
| No published ontology / empty catalogue | Run migrations, complete admin bootstrap, then submit/approve/publish actual courses. |
| SQL connection errors | Check URL encoding, secret version/access, SQL connection name/mount, runtime Cloud SQL Client role and completed migrations. |
| Source stays queued | Check task dispatcher IAM, queue path, worker URL/audience and scheduled re-dispatch. |
| Worker request 401/403 | Check task OIDC service account, its invoker binding and the Cloud Tasks service agent; do not make the worker public. |
| Upload rejected because scanner is missing | Expected production gate. Complete scanning integration in step 15. |
| Gemini job fails | Check configured model/region, Vertex API availability, runtime permissions, quotas and structured output evidence. |
| Cloud Build cannot push an image | Inspect the actual build identity and Artifact Registry permissions, not just the application runtime account. |
| Document parser finds no text | The source may be scanned/encrypted or unsupported; OCR must be configured, not simulated. |

## Completion record

Record these values in your private operations handoff, without passwords or tokens:

```text
Project / environment:
Region:
Frontend URL:
API URL / revision:
Private worker URL / revision:
Image digest:
SQL instance / database / migration revision:
Secret name and version (not value):
Verified admin UID:
Gemini model / region:
Active ontology version:
Maintenance schedules and owners:
Backup/restore drill date:
Smoke-test evidence and remaining launch gates:
```

A staging deployment is complete when the cloud journey in step 13 passes and real provider behavior is recorded. A public production launch additionally requires the feature/security/operational gates in step 15.
