import asyncio
import contextlib
import json
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Final, Self

from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, WebSocketException

from voice_to_voice.core.config import settings
from voice_to_voice.core.enums.connection_state import ConnectionState
from voice_to_voice.infra.speech_to_text.exceptions import (
    ConfigurationError,
    ConnectionError,
    STTError,
)
from voice_to_voice.schemas.stt import (
    InputAudioTranscription,
    Session,
    SessionConfig,
    TranscriptionSessionData,
    TurnDetection,
)
from voice_to_voice.utils.agents.cancel_token import CancellationToken

RETRY_ATTEMPTS: Final[int] = 5


class AsyncRealtimeSTT:
    """
    Async WebSocket client for OpenAI Realtime STT API.

    This class handles WebSocket connections to transcription services,
    sending audio data and receiving real-time transcription results.
    """

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        # on_partial: Callable[[str], Awaitable[None]],
        on_final: Callable[[str], Awaitable[None]],
        on_error: Callable[[Exception], Awaitable[None]] | None = None,
        on_connection_changed: Callable[[ConnectionState], Awaitable[None]]
        | None = None,
        on_interruption: Callable[[], Awaitable[None]] | None = None,
        cancel_token: CancellationToken | None = None,
        model: str = "gpt-4o-transcribe",
        server_prompt: str = "",
        threshold: float = 0.5,
        prefix_padding_ms: int = 300,
        silence_duration_ms: int = 300,
    ) -> None:
        """Initialize the AsyncRealtimeSTT."""
        if not endpoint.startswith("wss"):
            raise ConfigurationError("[STT] Endpoint must to be a websocket")

        self._url = endpoint
        self._headers = [("api-key", api_key)]
        self.cancel_token = cancel_token

        # Callbacks
        # self._on_partial = on_partial
        self._on_final = on_final
        self._on_error = on_error
        self._on_connection_changed = on_connection_changed
        self._on_interruption = on_interruption

        # Configuration
        self._cfg = SessionConfig(
            session=Session(
                input_audio_transcription=InputAudioTranscription(
                    model=model, prompt=server_prompt
                ),
                turn_detection=TurnDetection(
                    threshold=threshold,
                    prefix_padding_ms=prefix_padding_ms,
                    silence_duration_ms=silence_duration_ms,
                ),
            )
        )

        # Connection state
        self._ws: ClientConnection | None = None
        self._state = ConnectionState.DISCONNECTED
        self._receive_task: asyncio.Task | None = None

    async def _set_state(self, state: ConnectionState) -> None:
        """Update connection state and notify callback."""
        if self._state != state:
            self._state = state
            logger.debug(f"STT connection state changed to: {state.value}")
            if self._on_connection_changed:
                try:
                    await self._on_connection_changed(state)
                except Exception as e:
                    logger.error(f"Error in connection state callback: {e}")

    @retry(
        stop=stop_after_attempt(RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionClosed, WebSocketException)),
    )
    async def _establish_connection(self) -> ClientConnection:
        """Establish WebSocket connection with retry logic."""
        logger.debug("Connecting to STT service...")
        return await connect(self._url, additional_headers=self._headers)

    async def connect(self) -> None:
        """
        Connect to the WebSocket service and start receiving messages.

        Raises:
            ConnectionError: If connection fails after retries
        """
        if self._state in [ConnectionState.CONNECTED, ConnectionState.CONNECTING]:
            logger.warning("Already connected or connecting")
            return

        await self._set_state(ConnectionState.CONNECTING)

        try:
            self._ws = await self._establish_connection()
            await self._set_state(ConnectionState.CONNECTED)
            logger.debug("Connected to STT service")

            # Send session configuration
            await self._send_config()

            # Start receiving messages
            self._receive_task = asyncio.create_task(self._receive_loop())

        except Exception as e:
            await self._handle_error(ConnectionError(f"Connection failed: {e}"))
            await self._set_state(ConnectionState.DISCONNECTED)
            raise

    async def disconnect(self) -> None:
        """Disconnect from the WebSocket service."""
        logger.debug("Disconnecting from STT service")
        await self._set_state(ConnectionState.CLOSED)

        # Cancel receive task
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, RuntimeError):
                await self._receive_task

        # Close WebSocket
        if self._ws:
            try:
                await self._ws.close()
            except Exception as e:
                logger.error(f"Error closing STT WebSocket: {e}")

        self._ws = None

    async def __aenter__(self) -> Self:
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        traceback: TracebackType,
    ) -> None:
        """Async context manager exit."""
        await self.disconnect()

    async def _send_config(self) -> None:
        """Send session configuration to the service."""
        if not self._ws:
            raise ConnectionError("WebSocket is not connected")

        try:
            await self._ws.send(json.dumps(self._cfg.model_dump()))
            logger.debug("Session configuration sent")
        except Exception as e:
            raise ConnectionError(f"Failed to send configuration: {e}") from e

    async def send_audio(self, audio: str) -> None:
        """Send audio data to the transcription service."""
        if not self._ws or self._state != ConnectionState.CONNECTED:
            raise ConnectionError("WebSocket is not connected")

        if not audio:
            logger.warning("Empty audio data received")
            return

        try:
            payload = {"type": "input_audio_buffer.append", "audio": audio}
            await self._ws.send(json.dumps(payload))
        except ConnectionClosed as e:
            await self._set_state(ConnectionState.DISCONNECTED)
            raise ConnectionError("Connection closed while sending audio") from e
        except Exception as e:
            raise ConnectionError(f"Failed to send audio: {e}") from e

    async def flush_audio_buffer(self) -> None:
        """Flush the audio input buffer."""
        if not self._ws or self._state != ConnectionState.CONNECTED:
            raise ConnectionError("WebSocket is not connected")

        try:
            payload = {"type": "input_audio_buffer.clear"}
            await self._ws.send(json.dumps(payload))
            logger.debug("Audio buffer flushed")
        except Exception as e:
            raise ConnectionError(f"Failed to flush audio buffer: {e}") from e

    async def _receive_loop(self) -> None:
        """Receive and process messages from WebSocket."""
        if not self._ws:
            raise ConnectionError("WebSocket is not connected")

        try:
            while True:
                raw_message = await self._ws.recv(decode=True)
                await self._process_message(raw_message)
        except ConnectionClosed:
            logger.debug("WebSocket connection closed")
            await self._set_state(ConnectionState.DISCONNECTED)
        except asyncio.CancelledError:
            logger.debug("Receive loop cancelled")
        except Exception as e:
            logger.error(f"Error in receive loop: {e}")
            await self._set_state(ConnectionState.DISCONNECTED)
            await self._handle_error(ConnectionError(f"Error in receive loop: {e}"))

    async def _process_message(self, raw_message: str) -> None:
        """Process incoming WebSocket message."""
        try:
            data = json.loads(raw_message)
            session_data = TranscriptionSessionData.model_validate(data)
            event_type = session_data.type
            logger.debug(f"event type: {event_type}")

            if event_type == "input_audio_buffer.speech_started":
                if self.cancel_token:
                    self.cancel_token.cancel()
                    if self._on_interruption:
                        await self._on_interruption()

            # if event_type == "conversation.item.input_audio_transcription.delta":
            #     delta = session_data.delta
            #     if delta:
            #         await self._on_partial(delta)

            if event_type == "conversation.item.input_audio_transcription.completed":
                transcript = session_data.transcript
                if transcript:
                    logger.debug(f"user transcription: {transcript}")
                    await self._on_final(transcript)

            elif event_type == "error":
                error_msg = session_data.error
                await self._handle_error(STTError(f"Server error: {error_msg}"))

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON received: {e}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await self._handle_error(STTError(f"Message processing error: {e}"))

    async def _handle_error(self, error: Exception) -> None:
        """Handle errors and notify callback."""
        logger.error(f"STT client error: {error}")
        if self._on_error:
            try:
                await self._on_error(error)
            except Exception as e:
                logger.error(f"Error in error callback: {e}")

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected."""
        return self._state == ConnectionState.CONNECTED and self._ws is not None

    @property
    def connection_state(self) -> ConnectionState:
        """Get current connection state."""
        return self._state


def stt_client(
    on_final_callback: Callable[[str], Awaitable[None]],
    on_interruption: Callable[[], Awaitable[None]] | None = None,
    cancel_token: CancellationToken | None = None,
) -> AsyncRealtimeSTT:
    return AsyncRealtimeSTT(
        api_key=settings.AZURE_STT_API_KEY,
        endpoint=settings.AZURE_STT_ENDPOINT,
        model=settings.AZURE_STT_DEPLOYMENT,
        on_final=on_final_callback,
        on_interruption=on_interruption,
        cancel_token=cancel_token,
        server_prompt=settings.AZURE_STT_SERVER_PROMPT,
        threshold=settings.AZURE_STT_THRESHOLD,
        prefix_padding_ms=settings.AZURE_STT_PREFIX_PADDING_MS,
        silence_duration_ms=settings.AZURE_STT_SILENCE_DURATION_MS,
    )
