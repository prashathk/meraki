import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from google import genai
from google.genai import errors

from backend.meraki import gemini
from backend.meraki.extraction import extract


@pytest.fixture(autouse=True)
def isolated_gemini(monkeypatch, tmp_path):
    for name in ('GEMINI_PROVIDER', 'GEMINI_MODEL', 'GEMINI_API_KEY', 'GOOGLE_CLOUD_PROJECT', 'GOOGLE_CLOUD_LOCATION'):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(gemini, 'ENV_FILE', tmp_path / '.env')
    client = MagicMock()
    client.__enter__.return_value = client
    constructor = MagicMock(return_value=client)
    monkeypatch.setattr(genai, 'Client', constructor)
    return constructor, client


def test_missing_key_blocks_before_network(isolated_gemini):
    constructor, _ = isolated_gemini
    assert not gemini.status()['configured']
    with pytest.raises(ValueError, match='GEMINI_API_KEY'):
        gemini.generate_courses('text', {})
    constructor.assert_not_called()


@pytest.mark.parametrize('model', ['gemini-4-argon', 'gemini-latest', 'models/gemini-3.5-flash-lite', 'unknown'])
def test_non_allowlisted_models_block_before_network(monkeypatch, isolated_gemini, model):
    monkeypatch.setenv('GEMINI_API_KEY', 'test-secret')
    monkeypatch.setenv('GEMINI_MODEL', model)
    with pytest.raises(ValueError, match='blocked'):
        gemini.generate_courses('text', {})
    isolated_gemini[0].assert_not_called()


def test_local_env_changes_visible_without_restart(monkeypatch):
    assert not gemini.status()['configured']
    gemini.ENV_FILE.write_text('GEMINI_API_KEY=local-secret\nGEMINI_MODEL=gemini-3.5-flash-lite\n')
    assert gemini.status()['configured']
    assert gemini.configuration()['api_key'] == 'local-secret'
    assert 'local-secret' not in json.dumps(gemini.status())
    monkeypatch.setenv('GEMINI_API_KEY', 'exported-secret')
    assert gemini.configuration()['api_key'] == 'exported-secret'


@pytest.mark.parametrize('model', sorted(gemini.FREE_TIER_MODELS))
def test_developer_api_validates_evidence_and_tags(monkeypatch, isolated_gemini, model):
    constructor, client = isolated_gemini
    monkeypatch.setenv('GEMINI_API_KEY', 'test-secret')
    monkeypatch.setenv('GEMINI_MODEL', model)
    monkeypatch.setenv('GOOGLE_GENAI_USE_VERTEXAI', 'true')
    # A cloud project in the environment must not select Vertex implicitly.
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'unused-cloud-project')
    client.models.generate_content.return_value = SimpleNamespace(text=json.dumps({'courses': [
        {'title': 'BSc Computing', 'faculty': 'Invented faculty', 'evidence': 'BSc Computing', 'tags': ['technology', 'made-up']},
        {'title': 'Invented course', 'faculty': '', 'evidence': 'Invented course', 'tags': []},
    ]}))
    courses = extract('Faculty of Computing\nBSc Computing', 'gemini', [{'id': 'technology'}], 'Demo University')
    assert len(courses) == 1
    assert courses[0]['faculty'] == ''
    assert courses[0]['tags'] == ['technology']
    assert courses[0]['provider'] == 'Gemini Developer API / ' + model
    kwargs = constructor.call_args.kwargs
    assert kwargs['vertexai'] is False and kwargs['api_key'] == 'test-secret'
    assert kwargs['http_options'].retry_options.attempts == 1
    call = client.models.generate_content.call_args.kwargs
    assert call['model'] == model
    assert call['config']['response_mime_type'] == 'application/json'
    assert 'tools' not in call['config']
    client.models.generate_content.assert_called_once()


def test_quota_error_never_retries_or_falls_back(monkeypatch, isolated_gemini):
    monkeypatch.setenv('GEMINI_API_KEY', 'test-secret')
    constructor, client = isolated_gemini
    client.models.generate_content.side_effect = errors.ClientError(429, {'error': {'message': 'Sensitive test-secret'}})
    with pytest.raises(ValueError, match='quota or rate limit') as error:
        gemini.generate_courses('text', {})
    assert 'test-secret' not in str(error.value)
    constructor.assert_called_once()
    client.models.generate_content.assert_called_once()


@pytest.mark.parametrize('response', ['', 'not json', '{}', '{"courses": "wrong"}', '{"courses": [null]}'])
def test_invalid_model_output_fails_clearly(monkeypatch, isolated_gemini, response):
    monkeypatch.setenv('GEMINI_API_KEY', 'test-secret')
    isolated_gemini[1].models.generate_content.return_value = SimpleNamespace(text=response)
    with pytest.raises(ValueError, match='Gemini returned'):
        extract('BSc Computing', 'gemini', [], 'Demo University')


def test_vertex_requires_explicit_selection(monkeypatch, isolated_gemini):
    monkeypatch.setenv('GEMINI_PROVIDER', 'vertex')
    monkeypatch.setenv('GEMINI_MODEL', 'vertex-model')
    monkeypatch.setenv('GOOGLE_CLOUD_PROJECT', 'cloud-project')
    isolated_gemini[1].models.generate_content.return_value = SimpleNamespace(text='{"courses": []}')
    gemini.generate_courses('text', {})
    assert isolated_gemini[0].call_args.kwargs['vertexai'] is True
    assert not gemini.status()['free_tier_models_only']
