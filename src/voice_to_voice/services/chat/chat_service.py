import asyncio
import base64
from collections.abc import AsyncGenerator, AsyncIterable, Awaitable, Callable

from loguru import logger
from semantic_kernel.agents import ChatHistoryAgentThread
from semantic_kernel.contents import AuthorRole, ChatHistory

from voice_to_voice.core.config import settings
from voice_to_voice.core.enums.message import MessageType
from voice_to_voice.dto.chat import (
    ChatAnswer,
    ErrorMessage,
    InterruptMessage,
    VoiceAnswer,
)
from voice_to_voice.infra.sk.agent import agent
from voice_to_voice.infra.speech_to_text.speech_to_text import stt_client
from voice_to_voice.infra.text_to_speech.text_to_speech import tts_client
from voice_to_voice.schemas.agent import VoiceMessage
from voice_to_voice.utils.agents.cancel_token import CancellationToken
from voice_to_voice.utils.agents.transcription_event import TranscriptEvent


class ChatService:
    def __init__(
        self,
        send: Callable[[str], Awaitable[None]],
        receive: Callable[[], AsyncIterable],
        interrupt: bool = settings.INTERRUPT_AGENT,
    ) -> None:
        """Initializes ChatService."""
        self.send = send
        self.receive = receive
        self.loop = asyncio.get_running_loop()
        self.convo_id: str = ""
        self.thread = ChatHistoryAgentThread(ChatHistory())

        # Setup Interruption
        self.cancel_token = CancellationToken() if interrupt else None

        # Setup Voice-to-Voice pipeline Decoupling
        self.latest_transcript = ""
        self.transcript_event = TranscriptEvent()
        self._pipeline_task = asyncio.create_task(self.voice_agent_pipeline())

    async def voice_agent_pipeline(self) -> None:
        while True:
            await self.transcript_event.wait()
            self.transcript_event.reset()

            transcript = self.latest_transcript
            if transcript:
                try:
                    await self.run_voice_pipeline(transcript)
                except Exception as e:
                    logger.error(f"Pipeline error: {e}")

    async def send_error(self, error_type: str, message: str) -> None:
        await self.send(
            ErrorMessage(
                type=MessageType.ERROR,
                error=error_type,
                error_message=message,
            ).model_dump_json()
        )

    async def generate_completion(
        self,
        context: str,
    ) -> AsyncGenerator:
        try:
            async for chunk in agent.invoke_stream(
                messages=context,
                thread=self.thread,
            ):
                if not chunk:
                    continue
                yield str(chunk)
        except GeneratorExit:
            logger.debug("Streaming generator closed early (interruption).")
            return

    def on_audio_chunk(self, audio_data: bytes) -> None:
        try:
            audio = base64.b64encode(audio_data).decode("utf-8")

            async def send_message() -> None:
                await self.send(
                    VoiceAnswer(
                        type=MessageType.AUDIO_OUTPUT,
                        content=audio,
                    ).model_dump_json(by_alias=True)
                )

            asyncio.run_coroutine_threadsafe(send_message(), self.loop)

        except Exception as e:
            logger.error(f"Error in on_audio_chunk: {e}")

    async def generate_output(
        self,
        content: str,
    ) -> None:
        try:
            async with tts_client(self.cancel_token) as tts:
                tts.start_synthesis_streaming(self.on_audio_chunk)
                async for chunk in self.generate_completion(content):
                    if self.cancel_token and self.cancel_token.is_cancelled():
                        break
                    tts.write_text(chunk)
                    await self.send(
                        ChatAnswer(
                            type=MessageType.TEXT_OUTPUT,
                            role=AuthorRole.ASSISTANT,
                            content=chunk,
                        ).model_dump_json()
                    )
                await tts.finalize()
                logger.debug("TTS processing completed")
        except ConnectionError as e:
            logger.error(f"Error in processing synthesis: {e}")
            await self.send_error(
                error_type="TTSConnectionError",
                message="Failed to connect to the TTS service",
            )
            return
        except Exception as e:
            logger.error(f"Error in Initializing TTS service: {e}")
            await self.send_error(
                error_type="TTSRuntimeError",
                message=f"Unexpected error in TTS processing: {e}",
            )
            return

    async def run_voice_pipeline(
        self,
        transcript: str,
    ) -> None:
        await self.send(
            ChatAnswer(
                role=AuthorRole.USER,
                content=transcript,
                type=MessageType.USER_TRANSCRIPT,
            ).model_dump_json()
        )
        await self.generate_output(transcript)

    async def on_final_callback(self, transcript: str) -> None:
        """Enqueue transcription."""
        self.latest_transcript = transcript
        if self.cancel_token:
            self.cancel_token.reset()
        self.transcript_event.signal()

    async def run(self) -> None:
        async with stt_client(
            self.on_final_callback,
            on_interruption=self._on_stt_interrupt,
            cancel_token=self.cancel_token,
        ) as stt:
            async for msg in self.receive():
                try:
                    voice_message = VoiceMessage.model_validate(msg)
                    await stt.send_audio(voice_message.content)
                except Exception as e:
                    logger.error(f"Error processing audio in STT: {e}")

    async def _on_stt_interrupt(self) -> None:
        try:
            await self.send(
                InterruptMessage(type=MessageType.INTERRUPT).model_dump_json()
            )
        except Exception as e:
            logger.error(f"Error handling STT interrupt: {e}")
