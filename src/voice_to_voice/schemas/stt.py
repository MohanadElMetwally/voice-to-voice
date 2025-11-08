from typing import Literal

from pydantic import BaseModel, Field


class TranscriptionSessionData(BaseModel):
    """Base model for validating incoming WebSocket messages."""

    type: str | dict
    event_id: str | None = None
    session: dict | None = None
    audio_start_ms: int | None = None
    audio_end_ms: int | None = None
    item_id: str | None = None
    previous_item_id: str | None = None
    item: dict | None = None
    content_index: int | None = None
    transcript: str | None = None
    delta: str | None = None
    error: dict | None = None


class InputAudioTranscription(BaseModel):
    model: str
    prompt: str


class TurnDetection(BaseModel):
    type: Literal["server_vad"] = Field(default="server_vad")
    threshold: float = Field(ge=0.0, le=1.0)
    prefix_padding_ms: int = Field(ge=0)
    silence_duration_ms: int = Field(ge=0)


class Session(BaseModel):
    input_audio_format: Literal["pcm16"] = Field(default="pcm16")
    input_audio_transcription: InputAudioTranscription
    turn_detection: TurnDetection


class SessionConfig(BaseModel):
    type: Literal["transcription_session.update"] = Field(
        default="transcription_session.update"
    )
    session: Session
