"""Pluggable voice backends.

Ships with no heavy ML deps so the brain stays a small container. Real
backends are wired in here:

  * STT  — faster-whisper (local) or any HTTP STT service
  * TTS  — Piper (local) or ElevenLabs (cloud)

Until a backend is configured, these raise NotImplementedError so the voice
routes return a clear 501 instead of silently failing.
"""

from __future__ import annotations


class STTBackend:
    """Speech-to-text. Override ``transcribe`` to plug in a real engine."""

    name = "none"

    async def transcribe(self, audio: bytes, mime: str) -> str:
        raise NotImplementedError(
            "No STT backend configured. Plug in faster-whisper or an HTTP "
            "STT service in app/voice/backends.py."
        )


class TTSBackend:
    """Text-to-speech. Override ``synthesize`` to plug in a real engine."""

    name = "none"

    async def synthesize(self, text: str, voice: str | None = None) -> tuple[bytes, str]:
        """Returns ``(audio_bytes, mime_type)``."""
        raise NotImplementedError(
            "No TTS backend configured. Plug in Piper (local) or ElevenLabs "
            "(cloud) in app/voice/backends.py."
        )


def get_stt() -> STTBackend:
    return STTBackend()


def get_tts() -> TTSBackend:
    return TTSBackend()
