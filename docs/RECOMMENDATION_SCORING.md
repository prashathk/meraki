# Student preference scoring

New recommendations use `degree-category-score-coverage-v2`. Existing snapshots keep their stored results and original policy description.

## Inputs and private profile

The student chooses interest and aptitude tags and assigns each selected tag a percentage from 0 to 100, defaulting to 100. The interest contribution defaults to 70; the aptitude contribution is always its complement, 30 by default. The input control and all tag scores are available above the recommendation results, under **Personalize your recommendations**.

`PUT /api/profile` and `POST /api/recommendations` accept:

```json
{
  "tags": ["technology", "mathematics"],
  "scores": {"technology": 80, "mathematics": 60},
  "interest_contribution": 60
}
```

Omitted scores default to 100. The server derives the aptitude contribution and effective contributions. With selections in only one category, that category contributes 100 regardless of the configured split. Both configured and effective contributions are saved. An empty profile can be saved to clear preferences; a recommendation requires at least one selection.

Values must be finite JSON numbers from 0 to 100. Booleans, numeric strings, unknown tags, scores for unselected tags, and a contributing category with no positive selected score are rejected. A category with zero effective contribution can have zero scores. Only the signed-in student's profile can be modified.

## Degree calculation

For each category, sum the student's scores for matching degree tags, then divide by the number of **all unique degree tags in that category**. Unselected degree tags add zero to the numerator. Unrelated student selections do not change the denominator. Duplicate degree tags count once. An empty degree category has zero coverage and is not used as a divisor.

```text
interest coverage = matching interest score sum / degree interest count
aptitude coverage = matching aptitude score sum / degree aptitude count
preference match = interest coverage * interest contribution / 100
                 + aptitude coverage * aptitude contribution / 100
```

Example: a degree with two interests and two aptitudes, matched scores 80 and 60, and a 60/40 split has coverage 40% and 30%, giving **36% preference match**.

The policy rounds results to two decimal places, using half-up rounding, before ranking. Ties use case-sensitive title order and then course ID. Both the SQL query and final ranking use this policy **before** the 100-result limit. PostgreSQL uses decimal arithmetic and `C` collation; SQLite uses its numeric calculations and binary collation. The candidate cache key includes the selected tags, every score, configured contribution, category mapping, catalogue version, policy version and result limit.

## Snapshots and explanation

New history records contain selected tags and their labels, scores, configured and effective contributions, the catalogue version, the scoring-policy version and description, and the frozen ranked results. Each result includes matched score sums, degree category counts, coverage and contributions. **Why this matches**, history details and PDF exports show these stored values.

PDFs do not look up a current profile or recalculate a saved result. Earlier `selected-coverage-70-30-v1` PDFs retain the exact original description, including their student-selection denominators. Scores are a **preference match**, not admission probability or verified academic performance.

## Verification

Run the backend suite normally. `python -m scripts.verify_scoring_database` additionally checks the configured database with temporary, rolled-back fixture records, without changing the active catalogue. It covers six input cases and three result limits, including the 36% example, missing categories, duplicate tags, decimal rounding and tied titles. Use this deployment check on PostgreSQL as well as the local SQLite checks.
