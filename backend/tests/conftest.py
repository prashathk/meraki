"""Test identities use an ephemeral credential, never a published demo password."""
import os
import secrets

os.environ['DEMO_PASSWORD'] = secrets.token_urlsafe(24)
