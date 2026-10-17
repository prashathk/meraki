import secrets

import pytest

from backend.meraki import local_config


def test_demo_password_requires_private_configuration(monkeypatch, tmp_path):
    monkeypatch.delenv('DEMO_PASSWORD', raising=False)
    monkeypatch.setattr(local_config, 'ENV_FILE', tmp_path / '.env')
    with pytest.raises(RuntimeError, match='DEMO_PASSWORD'):
        local_config.demo_password()
    local_config.ENV_FILE.write_text('DEMO_PASSWORD=\n')
    with pytest.raises(RuntimeError, match='at least 12 characters'):
        local_config.demo_password()
    expected = secrets.token_urlsafe(24)
    local_config.ENV_FILE.write_text('DEMO_PASSWORD=' + expected + '\n')
    assert local_config.demo_password() == expected
    exported = secrets.token_urlsafe(24)
    monkeypatch.setenv('DEMO_PASSWORD', exported)
    assert local_config.demo_password() == exported


def test_local_setup_generates_and_preserves_private_values(monkeypatch, tmp_path, capsys):
    from dotenv import dotenv_values
    from scripts import configure_local
    monkeypatch.setattr(configure_local, 'ROOT', tmp_path)
    (tmp_path / '.env.example').write_text('DEMO_PASSWORD=\nPOSTGRES_PASSWORD=\nGEMINI_API_KEY=\n')
    configure_local.main()
    first = dotenv_values(tmp_path / '.env')
    assert len(first['DEMO_PASSWORD']) >= 12
    assert len(first['POSTGRES_PASSWORD']) >= 12
    configure_local.main()
    assert dotenv_values(tmp_path / '.env') == first
    output = capsys.readouterr().out
    assert first['DEMO_PASSWORD'] not in output
    assert first['POSTGRES_PASSWORD'] not in output
