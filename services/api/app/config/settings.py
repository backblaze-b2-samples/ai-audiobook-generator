from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    b2_endpoint: str = ""
    b2_region: str = ""
    b2_application_key_id: str = ""
    b2_application_key: str = ""
    b2_bucket_name: str = ""
    b2_public_url: str = ""

    # Text-to-speech. The active provider is chosen by `tts_provider`; its SDK
    # is lazy-imported by the matching adapter in repo/tts/. Provider API keys
    # are read from their conventional env vars (OPENAI_API_KEY /
    # ELEVENLABS_API_KEY); `tts_default_voice` picks the single narrator voice.
    tts_provider: str = "openai"
    openai_api_key: str = ""
    elevenlabs_api_key: str = ""
    tts_default_voice: str = ""

    api_port: int = 8000
    # Explicit allowlist by default — covers Next on :3000 and the
    # fallback :3001 it picks if 3000 is busy. Production deploys should
    # override with the exact frontend origin.
    api_cors_origins: str = "http://localhost:3000,http://localhost:3001"
    # Optional dev-only escape hatch: a regex that matches additional
    # allowed origins. Empty by default — set this to e.g.
    # `^http://localhost:\d+$` to accept any localhost port without
    # listing each one. NEVER ship this to production.
    api_cors_origin_regex: str = ""

    # Upload limits
    max_file_size: int = 100 * 1024 * 1024  # 100MB

    # Small durable counters (downloads, etc). Point at a persistent
    # volume in production if you care about surviving restarts.
    download_count_file: str = "data/download_count.json"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",")]


settings = Settings()
