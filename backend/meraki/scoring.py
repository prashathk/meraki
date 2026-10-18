"""Versioned preference scoring; snapshots contain all inputs, never live lookups."""
from decimal import Decimal, ROUND_HALF_UP
import math
from numbers import Real
from fastapi import HTTPException

POLICY_VERSION = 'degree-category-score-coverage-v2'
POLICY_DESCRIPTION = (
    'Interest coverage = matched interest score sum / the degree\'s unique interest count; '
    'aptitude coverage = matched aptitude score sum / the degree\'s unique aptitude count. '
    'Preference match = interest coverage x interest contribution / 100 + aptitude coverage x aptitude contribution / 100. '
    'Unselected degree tags contribute zero; an empty degree category contributes zero. '
    'A single selected category contributes 100%. Results are rounded to two decimal places before ranking; ties use title and course ID. '
    'This is a preference match, not an admission probability or verified academic performance. Eligibility remains unverified.'
)
# Preserve the exact description printed by pre-v2 PDFs.
LEGACY_POLICY_DESCRIPTION = 'Score: 70% selected-interest coverage + 30% selected-aptitude coverage; one-family inputs are renormalized. This is a preference match, not a probability of admission or success. Eligibility is unknown unless verified. Demo courses are illustrative.'


def percentage(value):
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value) or not 0 <= value <= 100:
        raise HTTPException(422, 'Percentages and scores must be finite numbers from 0 to 100')
    return float(value)


def inputs(tags, scores, interest_contribution, terms, allow_empty=False):
    contribution = percentage(interest_contribution)
    tags = sorted(set(tags))
    kinds = {t['id']: t['type'] for t in terms}
    if not set(tags) <= kinds.keys() or (not tags and not allow_empty):
        raise HTTPException(422, 'Choose at least one valid interest or aptitude')
    scores = scores or {}
    if not set(scores) <= set(tags):
        raise HTTPException(422, 'Scores can only be assigned to selected tags')
    scores = {tag: percentage(scores.get(tag, 100)) for tag in tags}
    selected = {kind: [t for t in tags if kinds[t] == kind] for kind in ('interest', 'aptitude')}
    effective = {'interest': contribution, 'aptitude': 100 - contribution}
    if not selected['interest']:
        effective = {'interest': 0.0, 'aptitude': 100.0 if tags else 0.0}
    elif not selected['aptitude']:
        effective = {'interest': 100.0, 'aptitude': 0.0}
    for kind in effective:
        if effective[kind] > 0 and not any(scores[t] > 0 for t in selected[kind]):
            raise HTTPException(422, f'Choose a positive {kind} score' + ('; a single selected category contributes 100%' if not all(selected.values()) else ' or set its contribution to zero'))
    return {'tags': tags, 'scores': scores, 'interest_contribution': contribution,
            'aptitude_contribution': 100 - contribution, 'contributions': effective,
            'scoring_version': POLICY_VERSION}


def rounded(value):
    return float(Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))


def score_course(course, preferences, terms):
    kinds = {t['id']: t['type'] for t in terms}
    degree_tags = set(course['tags'])
    matched = degree_tags & set(preferences['tags'])
    details = {}
    total = Decimal(0)
    for kind in ('interest', 'aptitude'):
        category = {t for t in degree_tags if kinds.get(t) == kind}
        score_sum = sum((Decimal(str(preferences['scores'][t])) for t in sorted(matched & category)), Decimal(0))
        coverage = score_sum / len(category) if category else Decimal(0)
        contribution = preferences['contributions'][kind]
        total += coverage * Decimal(str(contribution)) / 100
        details[kind] = {'matched_score_sum': float(score_sum), 'degree_count': len(category),
                         'coverage': float(coverage), 'contribution': contribution}
    return {**course, 'match': rounded(total), 'matched_tags': sorted(matched),
            'unmatched_tags': sorted(set(preferences['tags']) - degree_tags), 'eligibility': 'unknown',
            'scoring_version': POLICY_VERSION, 'scoring_details': details,
            'components': {kind: d['coverage'] for kind, d in details.items()}}


def number_text(value):
    return format(Decimal(str(value)).normalize(), 'f')
