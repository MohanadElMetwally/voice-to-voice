from collections.abc import Callable

from azure.cognitiveservices.speech import SpeechSynthesisEventArgs

from loguru import logger


class AudioEventHandler:
    @staticmethod
    def handle_audio_chunk(
        evt: SpeechSynthesisEventArgs, callback: Callable[[bytes], None]
    ) -> None:
        """Handle audio chunk from Azure SDK callback."""
        try:
            if evt.result and evt.result.audio_data:
                callback(evt.result.audio_data)
        except Exception as e:
            logger.error(f"Error handling audio chunk: {e}")

    @staticmethod
    def handle_synthesis_completed(
        evt: SpeechSynthesisEventArgs, token: Callable[[], None]
    ) -> None:
        """Handle synthesis completion."""
        token()
        logger.debug("TTS synthesis completed")

    @staticmethod
    def handle_synthesis_canceled(
        evt: SpeechSynthesisEventArgs, token: Callable[[], None]
    ) -> None:
        """Handle synthesis cancellation."""
        token()
        logger.error(f"TTS synthesis canceled: {evt.result.reason}")
