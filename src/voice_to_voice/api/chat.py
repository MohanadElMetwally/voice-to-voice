from collections.abc import AsyncGenerator
from typing import Any

from fastapi import (
    APIRouter,
    WebSocket,
)

from voice_to_voice.services.chat.chat_service import ChatService

router = APIRouter()


@router.websocket("/chat")
async def start_chat_ws(
    websocket: WebSocket,
) -> None:
    await websocket.accept()

    async def send_func(message: str) -> None:
        await websocket.send_text(message)

    async def receive_loop() -> AsyncGenerator[Any]:
        async for msg in websocket.iter_json():
            yield msg

    chat_service = ChatService(send_func, receive_loop)
    await chat_service.run()
