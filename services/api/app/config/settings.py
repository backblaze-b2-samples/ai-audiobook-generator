from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    b2_region: str = ""
    b2_application_key_id: str = ""
    b2_application_key: str = ""
    b2_bucket_name: str = ""
    b2_public_url_base: str = ""

    # Text-to-speech. The active provider is chosen by `tts_provider`; its SDK
    # is lazy-imported by the matching adapter in repo/tts/. Provider API keys
    # are read from their conventional env vars (OPENAI_API_KEY /
    # ELEVENLABS_API_KEY); `tts_default_voice` picks the single narrator voice.
    tts_provider: str = "openai"
    openai_api_key: str = ""
    elevenlabs_api_key: str = ""
    tts_default_voice: str = ""

    # Durable narration jobs. API requests enqueue work into Redis, and a
    # separate RQ worker process renders chapters from the B2 manifest.
    redis_url: str = "redis://localhost:6379/0"
    redis_socket_connect_timeout_seconds: float = 1.0
    redis_socket_timeout_seconds: float = 2.0
    redis_retry_count: int = 2
    redis_retry_backoff_base_seconds: float = 0.05
    redis_retry_backoff_cap_seconds: float = 0.2
    narration_queue_name: str = "narration"
    narration_job_timeout_seconds: int = 60 * 60
    narration_job_result_ttl_seconds: int = 24 * 60 * 60
    narration_job_failure_ttl_seconds: int = 7 * 24 * 60 * 60
    narration_lease_ttl_seconds: int = 10 * 60
    narration_tombstone_ttl_seconds: int = 24 * 60 * 60
    narration_resume_scan_enabled: bool = False
    narration_resume_scan_batch_size: int = 100
    narration_resume_scan_max_manifests: int = 1000
    narration_resume_scan_lease_ttl_seconds: int = 15 * 60

    # Minimal tenant auth for audiobook routes. Format:
    # "owner-a:token-a,owner-b:token-b". The frontend sends the matching
    # NEXT_PUBLIC_BOOK_OWNER and NEXT_PUBLIC_BOOK_TOKEN values.
    book_auth_tokens: str = ""

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

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def b2_s3_url(self) -> str:
        return f"https://s3.{self.b2_region}.backblazeb2.com"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",")]


settings = Settings()
