import asyncio

from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import (
    AzureChatCompletion,
    AzureChatPromptExecutionSettings,
)
from semantic_kernel.functions import KernelArguments

from voice_to_voice.core.config import settings

chat_completion = AzureChatCompletion(
    api_key=settings.AZURE_OPENAI_API_KEY,
    endpoint=settings.AZURE_OPENAI_ENDPOINT,
    deployment_name=settings.AZURE_OPENAI_DEPLOYMENT,
)
settings = AzureChatPromptExecutionSettings(temperature=0.1)
kernel = Kernel()


agent = ChatCompletionAgent(
    service=chat_completion,
    kernel=kernel,
    arguments=KernelArguments(settings),
)

USER_PROMPT = ">> "
AGENT_PROMPT = "Agent> "


async def main() -> None:
    user_input: str

    thread = None

    while True:
        try:
            user_input = input(USER_PROMPT)
        except (KeyboardInterrupt, EOFError):
            break

        if user_input == "q":
            break

        response = agent.invoke_stream(
            messages=user_input,
            thread=thread,
        )

        print(AGENT_PROMPT, end="")
        async for chunk in response:
            thread = chunk.thread
            print(str(chunk), end="")

        print()

    print("\n\nExiting chat...")

    await thread.delete() if thread else None


if __name__ == "__main__":
    asyncio.run(main())
