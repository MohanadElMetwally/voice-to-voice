from pydantic import BaseModel

from voice_to_voice.core.enums.message import MessageType


class VoiceMessage(BaseModel):
    type: MessageType
    content: str
