from pydantic import BaseModel
from semantic_kernel.contents import AuthorRole

from voice_to_voice.core.enums.message import MessageType


class ChatAnswer(BaseModel):
    type: MessageType
    role: AuthorRole
    content: str


class ErrorMessage(BaseModel):
    type: MessageType
    error: str
    error_message: str


class VoiceAnswer(BaseModel):
    type: MessageType
    role: AuthorRole = AuthorRole.ASSISTANT
    content: str


class InterruptMessage(BaseModel):
    type: MessageType
