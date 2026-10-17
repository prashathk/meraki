# Legacy prototype audit

The original Flask app stores selected preferences and results on the global app object, loads the ontology using a developer-specific path, interpolates form values into SPARQL, concatenates duplicate recommendation results and exposes whole-ontology regeneration publicly. Extraction mixes scraping, OCR, notebook-export functions and persistence in one module.

Behavior retained: degree-name search; interest and aptitude lookup; combined recommendation; detailed tags/university/faculty display; reset; ontology generation/querying intent.

The redevelopment separates private user state, source drafts and published snapshots. Regeneration is replaced by extraction -> review -> submission -> approval -> validated version activation. Scores use selected-preference coverage, with a labelled deterministic policy rather than presenting the legacy number as confidence probability.

The initial read-only audit found 23,768 triples and 201 degree concepts. Migration subsequently resolved all 10 shared concepts through reciprocal university/faculty restrictions, yielding 211 distinct course offerings without a Cartesian expansion. The active local catalogue now contains these offerings. See [migration report](LEGACY_MIGRATION_REPORT.md) for evidence, counts, tests and recovery.

Historical tags and affiliations are preserved with provenance; they are not independent confirmation of current admissions or university endorsement. Public links explicitly identify a university catalogue/homepage fallback rather than inventing degree-specific URLs.
