import asyncio
from collections.abc import Callable
from functools import partial
from types import TracebackType
from typing import Final, Self

import azure.cognitiveservices.speech as speechsdk
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from voice_to_voice.core.config import settings
from voice_to_voice.infra.text_to_speech.audio_event_handler import AudioEventHandler
from voice_to_voice.utils.agents.cancel_token import CancellationToken
from voice_to_voice.utils.voice.remove_formatting import clean_text

RETRY_ATTEMPTS: Final[int] = 5


class AsyncRealtimeTTS:
    """real-time text-to-speech streaming using Azure Speech Services."""

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        voice_name: str,
        cancel_token: CancellationToken | None = None,
    ) -> None:
        """Initialize the AsyncRealtimeTTS instance."""
        if not endpoint.startswith("wss"):
            raise ValueError("[TTS] Endpoint must be a websocket.")

        self.stream = speechsdk.audio.PullAudioOutputStream()
        self.audio_output_config = speechsdk.audio.AudioOutputConfig(stream=self.stream)
        self.speech_config = speechsdk.SpeechConfig(
            subscription=api_key, endpoint=endpoint
        )
        self.speech_config.speech_synthesis_voice_name = voice_name
        self.speech_config.set_speech_synthesis_output_format(
            speechsdk.SpeechSynthesisOutputFormat.Raw24Khz16BitMonoPcm
        )
        self.synthesizer: speechsdk.SpeechSynthesizer | None = None
        self.tts_request: speechsdk.SpeechSynthesisRequest | None = None
        self.tts_task: speechsdk.ResultFuture | None = None
        self._synthesis_event: asyncio.Event | None = None
        self._cancel_token: CancellationToken | None = cancel_token

    @retry(
        stop=stop_after_attempt(RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
    )
    def _setup_streaming(self) -> None:
        self.synthesizer = speechsdk.SpeechSynthesizer(
            speech_config=self.speech_config,
            audio_config=self.audio_output_config,
        )
        self.tts_request = speechsdk.SpeechSynthesisRequest(
            input_type=speechsdk.SpeechSynthesisRequestInputType.TextStream
        )

        self.tts_task = self.synthesizer.speak_async(self.tts_request)
        logger.debug("TTS streaming connection established")

    async def __aenter__(self) -> Self:
        """Initialize TTS streaming connection."""
        logger.debug("Initializing TTS streaming connection")
        if not self._cancel_token:
            self._synthesis_event = asyncio.Event()

        self._setup_streaming()

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        traceback: TracebackType,
    ) -> None:
        """Clean up TTS resources."""
        logger.debug("Cleaning up TTS resources")

        self.synthesizer = None

        if exc_type:
            logger.error(
                f"Exception during TTS context exit: {exc_type.__name__}: {exc_value}"
            )

    def start_synthesis_streaming(
        self, on_audio_chunk: Callable[[bytes], None]
    ) -> None:
        """Start streaming synthesis with audio chunk callback."""
        if not self.synthesizer:
            raise RuntimeError("TTS not initialized. Use within async context manager.")

        logger.debug("Starting synthesis streaming")

        self.synthesizer.synthesizing.connect(
            partial(AudioEventHandler.handle_audio_chunk, callback=on_audio_chunk)
        )
        self.synthesizer.synthesis_completed.connect(
            partial(
                AudioEventHandler.handle_synthesis_completed, token=self._signal_token
            )
        )
        self.synthesizer.synthesis_canceled.connect(
            partial(
                AudioEventHandler.handle_synthesis_canceled, token=self._signal_token
            )
        )

    def write_text(self, chunk: str) -> None:
        """Write text chunk to TTS stream."""
        if not self.tts_request or not self.tts_request.input_stream:
            raise RuntimeError("TTS request not initialized")
        cleaned_chunk = clean_text(chunk)
        if cleaned_chunk:
            self.tts_request.input_stream.write(chunk)

    async def finalize(self) -> None:
        """Finalize TTS processing and return result."""
        if not self.tts_task:
            raise RuntimeError("TTS task not initialized")

        logger.debug("Finalizing TTS processing")

        if self.tts_request and self.tts_request.input_stream:
            self.tts_request.input_stream.close()

        if self._cancel_token:
            await self._cancel_token.wait()
        elif self._synthesis_event:
            await self._synthesis_event.wait()

    def _signal_token(self) -> None:
        """Signal that synthesis has completed or was canceled."""
        try:
            if self._synthesis_event:
                self._synthesis_event.set()
            elif self._cancel_token:
                self._cancel_token.cancel()
            else:
                logger.warning("No completion or cancel token available to signal")
        except Exception as e:
            logger.error(f"Error signaling synthesis completion: {e}")


def tts_client(cancel_token: CancellationToken | None = None) -> AsyncRealtimeTTS:
    return AsyncRealtimeTTS(
        api_key=settings.AZURE_TTS_API_KEY,
        endpoint=settings.AZURE_TTS_ENDPOINT,
        voice_name=settings.AZURE_TTS_VOICE_NAME,
        cancel_token=cancel_token,
    )
