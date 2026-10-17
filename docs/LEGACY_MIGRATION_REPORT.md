# Original ontology migration — 17 October 2026

The original prototype ontology was migrated into the running local Meraki application using admin preview, staging, review decisions and validated publication. No cloud deployment was performed.

| University | Published historical offerings |
|---|---:|
| University of Kelaniya | 105 |
| University of Moratuwa | 20 |
| University of Sri Jayewardenepura | 86 |
| Total | 211 |

## Mapping and provenance

Source: `D:/Ayantha/MSc FYP/Application/Application/ontology.owl`, copied unchanged to `backend/fixtures/prototype-ontology.owl`. SHA-256: `72add5750dc072070bb9f2da8936f676e1f388660d663dde8ebccf62e4637af0`.

23,768 triples contain 201 degree concepts, 3 universities, 19 shared faculty classes (20 university/faculty associations), and 207 original terms (171 interests, 36 aptitudes). Ten concepts belong to two universities. Reciprocal university/faculty membership and degree restrictions resolve their actual pairings, producing 211 separate offerings, with zero unresolved mappings. The published graph distinguishes DegreeConcept from CourseOffering and includes typed University/Faculty relationships, original identifiers and PROV derivation links.

Original tags on shared degree concepts are shared historical assertions, not independently verified suitability labels for each university. All original taxonomy identities are preserved; exact existing label/type matches reuse canonical terms. Stable offering identifiers and checksum-keyed staging prevent duplicate imports.

## Review and recovery

211 revisions were approved through the admin decision API with an explicit structural migration reason. Six illustrative seed courses were archived from active discovery and remain recoverable in the previous version. Unrelated pending submissions were not approved. Imported organizations have historical-import status and no fabricated representative memberships.

Active migrated version: `16b9b787-c637-4e43-bdb8-174191e5ca16`.
Previous version: `067e2efc-6452-48d5-8792-e703773bcf3d`.

Consistent local SQLite backups are retained privately in `data/backups/`, including `before-legacy-ui-stage-20261017T141810Z.db` before staging and `before-legacy-20261017T141830Z.db` before publication. Admin **Ontology versions** can restore the previous version with a reason. Restore and subsequent reactivation were exercised successfully. Stop application writers before replacing a SQLite database from a backup.

## Functional verification

- All 20 backend tests passed, including migration preview permissions, XML entity rejection, exact graph pairings, idempotent staging, review/publication, distinct shared-course recommendations, readable PDF text, tenant isolation, typed RDF counts and version recovery.
- Production frontend TypeScript/Vite build passed.
- Browser upload, preview of 211 offerings, staging and review detail passed.
- Browser student checks passed against the actual migrated database: all three university counts, Chemistry search, image-free cards, searchable preferences, 100% Chemistry/Mathematics preference matches, PDF download and populated mobile width.
- Existing test coverage exercises multi-course source extraction, contact consent/activity attribution, comparison, saves, roles and publication. No external university message was sent by this migration.

Run `node scripts/verify_legacy_browser.mjs` with the local migrated API running to repeat the populated student checks. Evidence: `output/legacy-migration-result.json`, `output/legacy-migration-preview.png`, `output/legacy-migration-review.png`, `output/legacy-student-catalogue.png`, `output/legacy-student-recommendations.png`, and `output/legacy-student-shortlist.pdf`.

## Data limits

Historical ontology content is now available in the application; current course availability, admissions, fees and university affiliation have not been independently reverified. Public links use the Moratuwa undergraduate catalogue, Sri Jayewardenepura undergraduate catalogue or Kelaniya homepage, labelled accordingly. Exact degree-specific URLs were not invented. Match percentages describe selected-tag coverage, not admission probability. Fresh institutional source submissions can replace historical details through the existing extraction, review and approval workflow.
