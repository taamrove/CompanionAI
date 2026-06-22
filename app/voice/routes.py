"""Voice endpoints: /voice/transcribe (STT) and /voice/speak (TTS)."""

from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.voice.backends import get_stt, get_tts

router = APIRouter(prefix="/voice", tags=["voice"])


class SpeakRequest(BaseModel):
    text: str
    voice: str | None = None


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)) -> dict:
    audio = await file.read()
    try:
        text = await get_stt().transcribe(audio, file.content_type or "audio/wav")
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    return {"text": text}


@router.post("/speak")
async def speak(req: SpeakRequest) -> Response:
    try:
        audio, mime = await get_tts().synthesize(req.text, req.voice)
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc))
    return Response(content=audio, media_type=mime)
