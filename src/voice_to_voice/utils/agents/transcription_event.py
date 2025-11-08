import asyncio

class TranscriptEvent:
    def __init__(self) -> None:
        """Signal that a new finalized transcript is available."""
        self._event = asyncio.Event()

    def signal(self) -> None:
        """Trigger the event (notify pipeline)."""
        self._event.set()

    def reset(self) -> None:
        """Return to waiting state after pipeline handles it."""
        if self._event.is_set():
            self._event.clear()

    async def wait(self) -> None:
        """Await the next transcript signal."""
        await self._event.wait()

    def is_signaled(self) -> bool:
        return self._event.is_set()
