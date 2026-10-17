"""Private local development settings; exported values override the root .env."""
import os
from pathlib import Path

from dotenv import dotenv_values

ENV_FILE = Path(__file__).resolve().parents[2] / '.env'


def demo_password():
    value = os.environ.get('DEMO_PASSWORD')
    if value is None:
        value = dotenv_values(ENV_FILE).get('DEMO_PASSWORD')
    if not value or len(value) < 12:
        raise RuntimeError('Set a private DEMO_PASSWORD of at least 12 characters in the root .env, or run python -m scripts.configure_local.')
    return value
