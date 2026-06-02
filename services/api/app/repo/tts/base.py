"""Provider-agnostic text-to-speech interface.

Each concrete adapter lazy-imports its own SDK (mirroring how the metadata
service lazy-imports PyPDF2 / mutagen), so only the active provider's package
needs to be installed.
"""

from abc import ABC, abstractmethod

from app.types import Voice


class TTSError(Exception):
    """Raised when a TTS provider fails to synthesize or is misconfigured."""


class TTSProvider(ABC):
    """Single-narrator TTS provider. One voice narrates the whole book."""

    @abstractmethod
    def list_voices(self) -> list[Voice]:
        """Return the narrator voices this provider offers."""

    @abstractmethod
    def default_voice_id(self) -> str:
        """Return the voice id to use when the caller didn't pick one."""

    @abstractmethod
    def synthesize(self, text: str, voice_id: str) -> bytes:
        """Render `text` with `voice_id` and return MP3 audio bytes."""
