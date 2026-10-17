"""Explicitly initialize a cloud prototype with a verified Firebase administrator.

Only the optional, clearly marked fictional catalogue is populated. Local users,
passwords, sessions, uploads and activity are never copied into the deployment.
"""
import argparse
from backend.meraki.db import Session, Record, add
from backend.meraki.domain import catalogue, new_revision, publish
from scripts.bootstrap_admin import main as bootstrap_admin


def main(uid, email, name, demo_catalogue=False):
    bootstrap_admin(uid, email, name)
    if not demo_catalogue:
        return
    with Session() as db:
        if catalogue(db):
            raise ValueError('Refusing to replace an existing published catalogue')
        admin = db.get(Record, 'firebase:' + uid)
        organizations = {}
        for slug, label in [('northbridge', 'Northbridge University'), ('lakeside', 'Lakeside University')]:
            org = add(db, 'organization', {'name': label, 'contact': '', 'illustrative': True}, state='verified')
            organizations[slug] = org
        examples = [
            ('BSc Computer Science', 'Faculty of Computing', ['technology', 'mathematics', 'analytical-thinking'], 'northbridge'),
            ('BSc Information Systems', 'Faculty of Technology', ['technology', 'business', 'analytical-thinking', 'communication'], 'northbridge'),
            ('BA Digital Design', 'Faculty of Design', ['design', 'technology', 'creativity'], 'lakeside'),
            ('BSc Environmental Science', 'Faculty of Science', ['environment', 'mathematics', 'analytical-thinking'], 'lakeside'),
            ('BBA Business Management', 'Faculty of Business', ['business', 'communication', 'analytical-thinking'], 'northbridge'),
            ('BSc Data Science', 'Faculty of Computing', ['technology', 'mathematics', 'analytical-thinking'], 'northbridge'),
        ]
        for title, faculty, tags, slug in examples:
            org = organizations[slug]
            new_revision(db, {
                'title': title, 'university': org.data['name'], 'faculty': faculty,
                'tags': tags, 'course_url': f'https://{slug}.example/courses/' + title.lower().replace(' ', '-'),
                'url_mode': 'custom', 'mode': 'Full-time', 'duration': '3 years',
                'evidence': 'Illustrative demonstration course; not a real offering.',
                'provider': 'Prototype example', 'tag_origin': 'illustrative', 'illustrative': True,
            }, owner=admin.id, org=org.id, state='approved')
        publish(db, admin)
        print('Published six clearly marked illustrative prototype courses.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--uid', required=True)
    parser.add_argument('--email', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--demo-catalogue', action='store_true')
    args = parser.parse_args()
    main(args.uid, args.email, args.name, args.demo_catalogue)
