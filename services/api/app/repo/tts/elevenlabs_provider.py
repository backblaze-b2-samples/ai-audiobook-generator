"""ElevenLabs TTS adapter — optional alternate provider.

NOT installed by default. To use it: set TTS_PROVIDER=elevenlabs and run
`pip install elevenlabs`. The SDK is lazy-imported so the package is only
required when this provider is selected.
"""

from app.config import settings
from app.repo.tts.base import TTSError, TTSProvider
from app.types import Voice

_OUTPUT_FORMAT = "mp3_44100_128"
_MODEL = "eleven_multilingual_v2"


class ElevenLabsTTSProvider(TTSProvider):
    def __init__(self) -> None:
        self._api_key = settings.elevenlabs_api_key

    def _client(self):
        if not self._api_key:
            raise TTSError(
                "ELEVENLABS_API_KEY is not set — required for the ElevenLabs provider."
            )
        try:
            from elevenlabs.client import ElevenLabs
        except ImportError as e:  # pragma: no cover - install-time guard
            raise TTSError(
                "The `elevenlabs` package is not installed. "
                "Run `pip install elevenlabs`."
            ) from e
        return ElevenLabs(api_key=self._api_key)

    def list_voices(self) -> list[Voice]:
        client = self._client()
        try:
            result = client.voices.get_all()
        except Exception as e:
            raise TTSError(f"ElevenLabs voice listing failed: {e}") from e
        return [
            Voice(id=v.voice_id, name=v.name, description=getattr(v, "category", None))
            for v in result.voices
        ]

    def default_voice_id(self) -> str:
        if settings.tts_default_voice:
            return settings.tts_default_voice
        voices = self.list_voices()
        if not voices:
            raise TTSError("No ElevenLabs voices available for this account.")
        return voices[0].id

    def synthesize(self, text: str, voice_id: str) -> bytes:
        client = self._client()
        try:
            stream = client.text_to_speech.convert(
                voice_id=voice_id,
                text=text,
                model_id=_MODEL,
                output_format=_OUTPUT_FORMAT,
            )
            return b"".join(stream)
        except Exception as e:
            raise TTSError(f"ElevenLabs TTS synthesis failed: {e}") from e
