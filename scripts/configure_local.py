"""Prepare private local settings without displaying or replacing secrets."""
import secrets
from pathlib import Path

from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]


def main():
    path = ROOT / '.env'
    if not path.exists():
        path.write_text((ROOT / '.env.example').read_text(encoding='utf-8'), encoding='utf-8')
    settings = dotenv_values(path)
    for name in ('DEMO_PASSWORD', 'POSTGRES_PASSWORD'):
        if not settings.get(name):
            set_key(str(path), name, secrets.token_urlsafe(24))
            print(f'Generated {name} in the private root .env; value not displayed.')
    print('Local settings ready. Read DEMO_PASSWORD in your local .env to sign in; do not commit this file.')


if __name__ == '__main__':
    main()
