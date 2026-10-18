"""Check the configured SQL backend using disposable, rolled-back records.

Run after normal schema migration. No active catalogue pointer is changed, and
all fixture rows are rolled back even when a check fails. Works on PostgreSQL
and SQLite; intended for deployment verification as well as local checks.
"""
from backend.meraki.db import Session, VersionCourse, add, record
from backend.meraki.domain import TAXONOMY, new_revision, rank, _query_candidates


def main():
    with Session() as db:
        try:
            version = add(db, 'version', {'summary': 'Uncommitted scoring verification'}, state='published')
            fixtures = [
                ('degree-counts', 'Example', ['technology', 'business', 'mathematics', 'analytical-thinking']),
                ('z', 'Z full', ['technology', 'mathematics']),
                ('a', 'a full', ['technology', 'mathematics']),
                ('unicode', '\u00c1 full', ['technology', 'mathematics']),
                ('duplicate', 'Duplicate', ['technology', 'business', 'mathematics', 'analytical-thinking'] * 2),
                ('apt-only', 'Aptitude only', ['mathematics']),
                ('empty', 'Empty', []),
            ]
            courses = []
            for id, title, tags in fixtures:
                r = new_revision(db, {'title': title, 'tags': tags}, state='published', course_id=id)
                db.add(VersionCourse(version_id=version.id, course_id=id, revision_id=r.id))
                courses.append(record(r))
            db.flush()
            cases = [
                (['technology', 'mathematics'], {'technology': 80, 'mathematics': 60}, 60),
                (['technology', 'mathematics', 'design'], {'technology': 80, 'mathematics': 60, 'design': 100}, 60),
                (['technology', 'mathematics'], {}, 0),
                (['technology', 'mathematics'], {}, 100),
                (['technology'], {'technology': 1.005}, 70),
                (['mathematics'], {'mathematics': 60}, 100),
            ]
            example = rank(courses, cases[0][0], TAXONOMY, cases[0][1], 60)
            assert next(c['match'] for c in example if c['course_id'] == 'degree-counts') == 36
            for tags, scores, weight in cases:
                expected = rank(courses, tags, TAXONOMY, scores, weight)
                for limit in (1, 2, 100):
                    actual = _query_candidates(db, tags, version.id, limit, scores, weight, TAXONOMY)
                    assert [c['course_id'] for c in actual] == [c['course_id'] for c in expected[:limit]], 'SQL selection differs from final ranking'
                    actual = rank(actual, tags, TAXONOMY, scores, weight)
                    assert [(c['match'], c['scoring_details']) for c in actual] == [(c['match'], c['scoring_details']) for c in expected[:limit]]
            print(f'Scoring verified on {db.get_bind().dialect.name}: 6 cases x 3 limits, including the 36% example, decimal rounding, category counts and case-sensitive ties.')
        finally:
            db.rollback()


if __name__ == '__main__':
    main()
