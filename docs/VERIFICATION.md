# Verification record - 17 October 2026

## Passed

- **20 pytest cases:** deterministic/tag-family scoring; duplicate-free offerings; empty/invalid preferences; private recommendation reports; separate sessions/profiles; role and tenant denials; pending institution verification; one source -> three drafts; source/custom public URL semantics; frozen submissions; partial approval; publication and restore; failed-source preservation; event/enquiry retry deduplication; consent; dynamic taxonomy; missed-course entry; source cancellation; account-data deletion; unsafe private/metadata/IPv6 URL rejection.
- **3 Playwright journeys using installed Microsoft Edge:** home/student recommendations, image-free cards, comparison, PDF download and 390px mobile width; university multi-course extraction/review/link editing; admin review/version/analytics navigation.
- **Frontend TypeScript/production build:** passes. Firebase client is loaded separately to avoid inflating the initial app bundle.
- **Python compilation and `pip check`:** pass.
- **Alembic upgrade:** runs successfully against the local SQLite database.
- **Terraform:** `fmt`, `init -backend=false` and `validate` pass with pinned Google provider v6.50.0. No cloud plan/apply or resource creation.
- **Visual review:** inspected home and student desktop previews, the university review table and mobile preview. Generated screenshots live in `output/`. PDF content signature/text checked in API tests.
- **Legacy migration:** all 10 shared concepts resolved; 211 offerings published through review APIs, 207 taxonomy terms retained, typed RDF counts checked, repeat staging deduplicated, prior version restored and migrated version reactivated. Three added backend cases cover parsing, unsafe XML and the complete migration flow.
- **Populated catalogue browser check:** `node scripts/verify_legacy_browser.mjs` passed university counts (105/20/86), search, image-free cards, Chemistry/Mathematics 100% preference match, PDF download and 390px overflow check. Evidence is in `output/legacy-student-*`.

## Synthetic local performance

`python -m scripts.benchmark` uses a temporary SQLite database and FastAPI TestClient, adding 10,000 synthetic courses and issuing 50 concurrent recommendation requests from separate test identities. Results are capped at 100 ranked offerings.

| Measurement | Initial indexed query | Version-keyed immutable catalogue cache |
|---|---:|---:|
| Successful requests | 50 / 50 | 50 / 50 |
| p50 | 3.276 s | 0.879 s |
| p95 | 5.179 s | 1.429 s |
| Maximum | 5.400 s | 1.600 s |

Baseline and optimized reports are `output/benchmark-local-baseline.json` and `output/benchmark-local.json`. Cached data contains only immutable published course data; profiles, private history and results persist in the database. The published version UUID is part of the key, so publication/restore select the correct snapshot. This benchmark is not network latency, a broad-profile workload, or proof of Cloud SQL/Cloud Run capacity. Re-test on the target deployment and vary preference combinations/cache hit rate.

## Not verified live

Firebase production identity/email/MFA, Gemini output, Cloud Tasks OIDC dispatch, private Cloud Storage, Cloud SQL, backups/PITR, Docker image execution, Terraform apply, institutional source permissions and real-world user impact. Providers/configuration exist where noted; no credentials or billing authorization were supplied. No production NER corpus/model was trained and OCR is not silently simulated.

## Known test warning

The installed Starlette version warns that its `httpx` TestClient integration is deprecated in favor of `httpx2`. Tests currently pass; migrate the test dependency path during dependency maintenance. This warning is unrelated to live API request handling.

## Event definitions

Search includes generated recommendations and debounced catalogue searches (query length only, no raw search text). Course view means opening a course's detailed match/evidence explanation, or calling the course-detail API; card impressions are not counted as views. Explore-course clicks, opening the enquiry form (contact intent) and submitting an explicitly consented enquiry are separate events. Course-scoped activity is attributed to its owning university; a generic catalogue search is not falsely attributed to an institution.

## Midnight Focus theme update

Production frontend build passed. `node scripts/verify_theme_browser.mjs` passed dark/light rendering, navigation switching, local preference persistence after reload and 390px mobile overflow checks for student, university and administrator roles. Desktop and mobile screenshots are saved as `output/midnight-*`. The migrated catalogue recommendation/PDF browser verification also passed after the theme update. Dark is the default; both palettes share one layout and the saved choice applies across roles and public/auth pages.
