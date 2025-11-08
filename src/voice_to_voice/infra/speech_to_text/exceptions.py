class STTError(Exception):
    """Base exception for STT client errors."""


class ConnectionError(STTError):
    """Raised when connection fails."""


class ConfigurationError(STTError):
    """Raised when configuration is invalid."""
