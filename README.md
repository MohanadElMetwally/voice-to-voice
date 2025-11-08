# Voice‑to‑Voice Agent

Real‑time voice conversation with an AI agent over WebSocket. This project turns microphone audio into text using Azure OpenAI Realtime Transcription (gpt‑4o‑transcribe), streams the text to an Azure OpenAI chat model via Semantic Kernel, then synthesizes the model’s reply back to audio using Azure Cognitive Services Speech. Includes an optional interruption mechanism so users can cut off the AI mid‑speech just by speaking.

## Highlights

- End‑to‑end voice pipeline: Speech‑to‑Text → Chat Completion → Text‑to‑Speech
- Realtime, streaming UX over a single WebSocket: `/api/v1/chat`
- Interruption support (talk over the agent to interrupt its TTS)

## Architecture

Flow overview:

1. Client captures mic audio, encodes as base64 PCM16 chunks, and sends JSON messages over WebSocket to `/api/v1/chat`.
2. Server forwards audio to Azure OpenAI Realtime Transcription (gpt‑4o‑transcribe, websocket).
3. When a final transcript arrives, it’s queued into a pipeline.
4. The Semantic Kernel agent streams the AI response tokens from your Azure OpenAI chat deployment.
5. Azure Cognitive Services Speech synthesizes the streamed text into audio, which the server relays to the client as base64 PCM (`Raw24Khz16BitMonoPcm`).
6. If the user starts speaking again, server VAD triggers an interruption: current TTS is signaled to stop and the client receives an `INTERRUPT` message.

## Requirements

- Python 3.11+
- Azure OpenAI:
	- A Chat Completions deployment (e.g., GPT‑4o or GPT‑4‑series) for text responses
	- A Realtime Transcription (websocket) deployment for `gpt-4o-transcribe`
- Azure Cognitive Services Speech resource for Text‑to‑Speech

Python dependencies (managed in `pyproject.toml`):

- fastapi[standard]
- websockets
- azure-cognitiveservices-speech
- semantic-kernel==1.30
- pydantic-settings
- tenacity, loguru

## Environment variables

Create a `.env` file at the repository root

Required for Azure OpenAI (Chat):

- `AZURE_OPENAI_ENDPOINT` — Your Azure OpenAI endpoint URL
- `AZURE_OPENAI_API_KEY` — API key for Azure OpenAI
- `AZURE_OPENAI_DEPLOYMENT` — Name of your Chat Completions deployment
- `OPENAI_API_VERSION` — API version (optional; may be required depending on SDK config)

Required for Realtime STT (gpt‑4o‑transcribe):

- `AZURE_STT_ENDPOINT` — WebSocket endpoint (must start with `wss://`) for your transcribe deployment
- `AZURE_STT_API_KEY` — API key used as `api-key` header
- `AZURE_STT_DEPLOYMENT` — Deployment/model name (e.g., `gpt-4o-transcribe`)
- `AZURE_STT_SERVER_PROMPT` — Initial system/prompt text for transcription (optional)
- `AZURE_STT_THRESHOLD` — VAD threshold [0.0–1.0]
- `AZURE_STT_PREFIX_PADDING_MS` — VAD prefix padding in ms
- `AZURE_STT_SILENCE_DURATION_MS` — VAD silence duration in ms

Required for Azure Cognitive Services Speech (TTS):

- `AZURE_TTS_ENDPOINT` — WebSocket endpoint (must start with `wss://`) for speech synthesis
- `AZURE_TTS_API_KEY` — Speech resource key
- `AZURE_TTS_VOICE_NAME` — Voice name (e.g., `en-US-JennyNeural`)

Interruption:

- `INTERRUPT_AGENT` — `true`/`false` (default `false`); when `true`, speaking again interrupts in‑progress TTS

Notes:

- STT and TTS endpoints must be secure websockets (`wss://`).
- The `.env` file is loaded from the project root automatically.

## Run locally

Install dependencies and start the server. The project uses FastAPI’s CLI (provided by `fastapi[standard]`).

```
# create and activate a virtual environment, then:
uv sync

# run the app
fastapi run src/voice_to_voice/main.py
```

The API will be available at:

- WebSocket: `ws://localhost:8000/api/v1/chat`

Tip: If you previously used a hyphen in the path (`src/voice-to-voice/main.py`), replace it with an underscore: the correct path is `src/voice_to_voice/main.py`.

## WebSocket protocol

Connect to `ws://<host>:8000/api/v1/chat` and exchange JSON messages.

Client → Server (send audio chunks):

```
{
	"type": "AUDIO_INPUT",
	"content": "<base64-of-pcm16-audio>"
}
```

Server → Client (examples):

- Final user transcript (echo):

```
{ "type": "USER_TRANSCRIPT", "role": "user", "content": "what’s the weather" }
```

- Streaming text tokens from the agent:

```
{ "type": "TEXT_OUTPUT", "role": "assistant", "content": "The weather is…" }
```

- Streaming audio chunks (base64, `Raw24Khz16BitMonoPcm`):

```
{ "type": "AUDIO_OUTPUT", "role": "assistant", "content": "<base64-of-pcm16-audio>" }
```

- Interruption signal (when user speaks over the agent):

```
{ "type": "INTERRUPT" }
```

- Error message:

```
{ "type": "ERROR", "error": "TTSConnectionError", "error_message": "..." }
```
