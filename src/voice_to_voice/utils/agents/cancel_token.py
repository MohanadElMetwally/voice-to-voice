import asyncio


class CancellationToken:
    def __init__(self) -> None:
        """Initialize CancellationToken."""
        self._event = asyncio.Event()

    def cancel(self) -> None:
        self._event.set()

    def reset(self) -> None:
        if self._event.is_set():
            self._event.clear()

    async def wait(self) -> None:
        await self._event.wait()

    def is_cancelled(self) -> bool:
        return self._event.is_set()
