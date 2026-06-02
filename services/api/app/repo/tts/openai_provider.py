"""OpenAI TTS adapter — the default narration provider.

The `openai` SDK is lazy-imported inside methods so the package is only needed
when this provider is actually selected.
"""

from app.config import settings
from app.repo.tts.base import TTSError, TTSProvider
from app.types import Voice

# OpenAI's built-in voice catalog (stable names, no network call needed to
# enumerate). Descriptions are short narrator-oriented hints.
_VOICES = [
    Voice(id="alloy", name="Alloy", description="Neutral, balanced narrator"),
    Voice(id="echo", name="Echo", description="Warm, measured"),
    Voice(id="fable", name="Fable", description="Expressive, storyteller"),
    Voice(id="onyx", name="Onyx", description="Deep, authoritative"),
    Voice(id="nova", name="Nova", description="Bright, energetic"),
    Voice(id="shimmer", name="Shimmer", description="Soft, gentle"),
]

_MODEL = "tts-1"
_FORMAT = "mp3"


class OpenAITTSProvider(TTSProvider):
    def __init__(self) -> None:
        self._api_key = settings.openai_api_key

    def list_voices(self) -> list[Voice]:
        return list(_VOICES)

    def default_voice_id(self) -> str:
        return settings.tts_default_voice or _VOICES[0].id

    def synthesize(self, text: str, voice_id: str) -> bytes:
        if not self._api_key:
            raise TTSError(
                "OPENAI_API_KEY is not set — required for the OpenAI TTS provider."
            )
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover - install-time guard
            raise TTSError(
                "The `openai` package is not installed. Run `pip install openai`."
            ) from e

        client = OpenAI(api_key=self._api_key)
        try:
            response = client.audio.speech.create(
                model=_MODEL,
                voice=voice_id,
                input=text,
                response_format=_FORMAT,
            )
            return response.read()
        except Exception as e:
            raise TTSError(f"OpenAI TTS synthesis failed: {e}") from e
