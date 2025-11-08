from enum import StrEnum, auto


class ConnectionState(StrEnum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    RECONNECTING = auto()
    CLOSED = auto()
