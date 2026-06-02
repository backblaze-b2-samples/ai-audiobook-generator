"""TTS provider factory.

Selects the concrete adapter from `settings.tts_provider` (default `openai`).
Adapters are constructed lazily so importing this package never pulls in a
provider SDK.
"""

from app.config import settings
from app.repo.tts.base import TTSError, TTSProvider

_DEFAULT = "openai"


def get_provider(name: str | None = None) -> TTSProvider:
    provider = (name or settings.tts_provider or _DEFAULT).strip().lower()
    if provider == "openai":
        from app.repo.tts.openai_provider import OpenAITTSProvider

        return OpenAITTSProvider()
    if provider == "elevenlabs":
        from app.repo.tts.elevenlabs_provider import ElevenLabsTTSProvider

        return ElevenLabsTTSProvider()
    raise TTSError(
        f"Unknown TTS provider '{provider}'. Supported: openai, elevenlabs."
    )


__all__ = ["TTSError", "TTSProvider", "get_provider"]
