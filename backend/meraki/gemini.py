"""Explicit Gemini providers; the local Developer API uses a free-tier model allowlist.

Model eligibility is not a billing guarantee: use a key from an AI Studio Free
Tier project. There is no automatic provider/model fallback or paid tool use.
"""
import os
from pathlib import Path

from dotenv import dotenv_values

# Verified against https://ai.google.dev/gemini-api/docs/pricing on 2026-10-17.
# Pin exact model IDs: preview/latest aliases can change pricing or capabilities.
FREE_TIER_MODELS = frozenset({'gemini-3.5-flash-lite', 'gemini-3.8-flash'})
DEFAULT_MODEL = 'gemini-3.5-flash-lite'
ENV_FILE = Path(__file__).resolve().parents[2] / '.env'


def configuration():
    # Read Gemini settings for each request/job so API and worker pick up local
    # key changes together. Exported environment values take precedence.
    values = {**dotenv_values(ENV_FILE), **os.environ}
    provider = (values.get('GEMINI_PROVIDER') or 'developer').strip()
    model = (values.get('GEMINI_MODEL') or (DEFAULT_MODEL if provider == 'developer' else '')).strip()
    key = (values.get('GEMINI_API_KEY') or '').strip()
    project = (values.get('GOOGLE_CLOUD_PROJECT') or '').strip()
    error = ''
    if provider == 'developer':
        if model not in FREE_TIER_MODELS:
            error = 'This Gemini model is blocked. Choose gemini-3.5-flash-lite or gemini-3.8-flash, which are approved for free-tier use.'
        elif not key:
            error = 'Gemini is not configured. Add GEMINI_API_KEY from an AI Studio Free Tier project to the root .env file, or choose the NLP baseline.'
    elif provider == 'vertex':
        # Retain the existing cloud adapter only through explicit configuration.
        if not project or not model:
            error = 'Vertex AI is not configured. Set GOOGLE_CLOUD_PROJECT and GEMINI_MODEL, or choose the NLP baseline.'
    else:
        error = 'Unknown Gemini provider. Use developer for Google AI Studio or vertex for Google Cloud.'
    return {
        'provider': provider, 'model': model, 'api_key': key, 'project': project,
        'location': values.get('GOOGLE_CLOUD_LOCATION') or 'us-central1',
        'configured': not error, 'configuration_error': error,
    }


def status():
    config = configuration()
    return {name: config[name] for name in ('provider', 'model', 'configured', 'configuration_error')} | {
        'free_tier_models_only': config['provider'] == 'developer',
        'billing_tier_verified': False,
    }


def require_configuration():
    config = configuration()
    if not config['configured']:
        raise ValueError(config['configuration_error'])
    return config


def generate_courses(prompt, schema):
    from google import genai
    from google.genai import errors, types

    config = require_configuration()
    options = types.HttpOptions(timeout=60000, retry_options=types.HttpRetryOptions(attempts=1))
    if config['provider'] == 'developer':
        # Explicit False avoids GOOGLE_GENAI_USE_VERTEXAI changing the backend.
        client = genai.Client(vertexai=False, api_key=config['api_key'], http_options=options)
    else:
        client = genai.Client(vertexai=True, project=config['project'], location=config['location'], http_options=options)
    try:
        with client:
            response = client.models.generate_content(
                model=config['model'], contents=prompt,
                config={'response_mime_type': 'application/json', 'response_schema': schema,
                        'temperature': 0, 'max_output_tokens': 8192},
            )
    except errors.APIError as error:
        # Never persist SDK exception text: it can contain request/credential data.
        if error.code == 429:
            raise ValueError('Gemini quota or rate limit reached. Try later or select the local NLP baseline. No alternate model or paid service was attempted.') from None
        if error.code in (401, 403):
            raise ValueError('Gemini access was denied. Check the server API key, its restrictions and project access in AI Studio.') from None
        if error.code == 404:
            raise ValueError('The configured Gemini model is unavailable for this project. Check model access in AI Studio or use the NLP baseline.') from None
        raise ValueError('Gemini could not complete extraction. Check model availability and the source format, then retry or use the NLP baseline.') from None
    except Exception:
        raise ValueError('Gemini could not be reached or returned an invalid response. Retry later or use the NLP baseline.') from None
    if not response.text:
        raise ValueError('Gemini returned no course data. Try a clearer source or use the NLP baseline.')
    return response.text, f"Gemini Developer API / {config['model']}" if config['provider'] == 'developer' else f"Gemini Vertex AI / {config['model']}"
