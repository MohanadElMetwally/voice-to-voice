from enum import StrEnum, auto


class MessageType(StrEnum):
    AUDIO_INPUT = auto()
    INTERRUPT = auto()
    ERROR = auto()
    USER_TRANSCRIPT = auto()
    TEXT_OUTPUT = auto()
    AUDIO_OUTPUT = auto()
