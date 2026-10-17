# Meraki implementation status

Updated 17 October 2026. Checkmarks describe implementation, not live cloud certification.

## Working locally

- [x] Original Flask code inspected; references and logo preserved.
- [x] React/TypeScript/Tailwind frontend with responsive public home, role entry points and three workspaces.
- [x] Private development accounts, hashed passwords, expiring/revocable sessions, pending university verification and server-side authorization.
- [x] Firebase sign-in/onboarding/token-verification adapters; development identity forbidden in production.
- [x] Persistent courses, tag edges, revisions, active ontology versions and audit events (SQLite locally; PostgreSQL driver/configuration available).
- [x] Interest, aptitude, degree-name search; deterministic combined recommendation scoring; match explanations; image-free course cards.
- [x] Saved courses, comparison, profile reset, private recommendation history and downloadable PDF.
- [x] Consented in-app enquiries and aggregate first-party activity analytics with event/enquiry deduplication.
- [x] Multi-course document extraction, durable jobs, editable extracted list, per-degree source/custom public URL and selected batch submission.
- [x] NLP lexical baseline, optional trained spaCy adapter and reproducible training/evaluation scripts; structured Gemini extraction adapter.
- [x] Per-record approval/changes/rejection, frozen submitted records, new revisions and partial batch publication.
- [x] SHACL-gated RDF snapshot publication, optimistic concurrency on active pointer, checksum validation on restore and audit history.
- [x] Local/private cloud blob adapters, Cloud Tasks dispatcher and private worker endpoint implementation.
- [x] Legacy ontology migration: 23,768 triples, 201 concepts -> 211 historical offerings. All 10 shared concepts resolved by reciprocal graph assertions; provenance, admin review, version publication and recovery tested.
- [x] Local API, browser and build verification; desktop/mobile screenshots in output.
- [x] Catalogue retirement, adding taxonomy terms, manual missed-course drafts, source refresh/cancellation, stale-lease maintenance and application-account deletion with enquiry redaction.
- [x] Persistent coarse action budgets; production malware-scanner gate; bounded immutable-public-candidate cache keyed by ontology version.
- [x] Terraform formatting/init/provider validation passed without provisioning.
- [x] Local 10,000-synthetic-course/50-request benchmark: 50/50 successful, p95 1.429 seconds after immutable-public-candidate caching (baseline 5.179 seconds). Not a Cloud Run capacity claim.
- [x] Docker/Compose, Alembic, Firebase Hosting, Cloud Build and Terraform source.

## Requires external inputs or release hardening

- [ ] Live Google Cloud/Firebase/Gemini/Cloud Tasks/Cloud Storage verification; credentials, project and billing are not configured.
- [ ] Run PostgreSQL integration and Docker image/Compose checks; local Docker engine was unavailable. Terraform source validation passed; a credentialed plan/apply was not run.
- [ ] Train and validate production NER on permissioned university sources. The runnable baseline is explicitly not a trained NER model.
- [ ] OCR and malware scanning provider setup; scanned PDFs return an explicit unsupported state. Do not enable broad public ingestion until scanning and parser resource isolation are verified.
- [ ] Replace demo catalogue with university-reviewed sources and real public URLs. `.example` demo links intentionally do not represent real offerings.
- [ ] Independent institutional verification of current availability, admissions, original heuristic tags and exact public degree URLs. Structural legacy migration is complete; fallback links and historical status are explicit.
- [ ] Advanced optional filters (budget/location/formal eligibility), localization, automated refresh scheduling, taxonomy editing/retirement and richer graph visualization.
- [ ] Production MFA policy, password recovery via configured Firebase, edge-level auth abuse controls, retention/provider-identity-deletion verification and penetration testing.
- [ ] Validate deployed Cloud SQL/Cloud Run target load and subgroup usefulness/extraction quality with real pilot participants. Synthetic local target was tested separately.
- [ ] Bulk manual import, OCR and external email delivery integrations. Single missed-course entry and stale task lease recovery are implemented.
- [ ] HTML/CSS PDF renderer alternative. Current PDF uses ReportLab for deterministic portable output; core PDF download works locally.
- [ ] Accessibility audit beyond keyboard labels, responsive checks and automated browser smoke coverage.

## Important architectural scope

`records` is a typed aggregate/document table with indexed ownership/state columns, not a fully normalized domain schema. Course-tag edges and version membership have dedicated relational tables. Immutable published revision references provide history; draft edits have revision counters. This is a local functional MVP, not a claim of complete production readiness against every item in the master prompt. See README and deployment gates.
