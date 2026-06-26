from pathlib import Path

from app.config import Settings
from app.repo import b2_client


def test_settings_derives_b2_s3_url_and_ignores_legacy_endpoint(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "B2_ENDPOINT=https://s3.legacy.backblazeb2.com\n",
        encoding="utf-8",
    )

    loaded = Settings(_env_file=env_file, b2_region="us-west-004")

    assert not hasattr(loaded, "b2_endpoint")
    assert loaded.b2_s3_url == "https://s3.us-west-004.backblazeb2.com"


def test_env_example_uses_standard_b2_variable_names():
    env_example = Path(__file__).resolve().parents[3] / ".env.example"
    contents = env_example.read_text(encoding="utf-8")

    assert "B2_ENDPOINT" not in contents
    assert "B2_PUBLIC_URL=" not in contents
    assert "B2_PUBLIC_URL_BASE=" in contents


def test_public_url_uses_standard_base_name(monkeypatch):
    monkeypatch.setattr(
        b2_client.settings,
        "b2_public_url_base",
        "https://files.example.com/audiobooks/",
    )

    assert (
        b2_client._public_url("books/my chapter.mp3")
        == "https://files.example.com/audiobooks/books/my%20chapter.mp3"
    )


def test_s3_client_uses_derived_endpoint_and_sample_user_agent(monkeypatch):
    captured = {}

    def fake_client(service_name, **kwargs):
        captured["service_name"] = service_name
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(b2_client.settings, "b2_region", "us-west-004")
    monkeypatch.setattr(b2_client.settings, "b2_application_key_id", "key-id")
    monkeypatch.setattr(b2_client.settings, "b2_application_key", "key")
    monkeypatch.setattr(b2_client.boto3, "client", fake_client)

    b2_client.get_s3_client.cache_clear()
    try:
        b2_client.get_s3_client()
    finally:
        b2_client.get_s3_client.cache_clear()

    assert captured["service_name"] == "s3"
    assert captured["endpoint_url"] == "https://s3.us-west-004.backblazeb2.com"
    assert captured["region_name"] == "us-west-004"
    assert captured["config"].user_agent_extra == (
        "b2ai-ai-audiobook-generator (backblaze-b2-samples)"
    )
