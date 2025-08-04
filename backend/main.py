import os
import sys
import logging
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from websockets.exceptions import ConnectionClosedError

from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.audio.vad.silero import SileroVADAnalyzer, VADParams
from pipecat.frames.frames import (
    InputAudioRawFrame,
    OutputAudioRawFrame,
    InputTextRawFrame,
    LLMTextFrame,
    TTSTextFrame,
)
from pipecat.serializers.base_serializer import FrameSerializer, FrameSerializerType

from backend.pipelines.factory import build_pipeline
from backend.routers import menu, orders

# ── Windows selector loop (avoid Win SIGINT error) ------------------------
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ── Load .env & configure logging ------------------------------------------
load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cafe-agent")

# ── FastAPI setup & routers ------------------------------------------------
app = FastAPI(title="Sunrise Café AI – Phase-1")
app.include_router(menu.router, prefix="/api")
app.include_router(orders.router, prefix="/api")

# ── PCM Serializer for AUDIO -----------------------------------------------
class PCM(FrameSerializer):
    @property
    def type(self) -> FrameSerializerType:
        return FrameSerializerType.BINARY

    async def serialize(self, frame):
        if isinstance(frame, OutputAudioRawFrame):
            return frame.audio
        return None

    async def deserialize(self, data: bytes):
        return InputAudioRawFrame(audio=data, sample_rate=16_000, num_channels=1)

# ── Text Serializer for TEXT channel --------------------------------------
class TextSerializer(FrameSerializer):
    @property
    def type(self) -> FrameSerializerType:
        return FrameSerializerType.TEXT

    async def serialize(self, frame) -> str | None:
        # Outbound: LLM text & TTS text
        if isinstance(frame, LLMTextFrame):
            return frame.text
        if isinstance(frame, TTSTextFrame):
            return frame.text
        # (Frontend typically handles displaying user transcripts separately)
        return None

    async def deserialize(self, data: str | bytes):
        text = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
        return InputTextRawFrame(text=text)

# ── Transports -------------------------------------------------------------
class CafeTransport(FastAPIWebsocketTransport):
    async def _receive_messages(self):
        try:
            while self._ws and not self._closed:
                msg = await self._ws.receive()
                if (b := msg.get("bytes")):
                    await self.push_audio_frame(InputAudioRawFrame(b, 16_000, 1))
        except (WebSocketDisconnect, ConnectionClosedError):
            return

class TextOnlyTransport(FastAPIWebsocketTransport):
    async def _receive_messages(self):
        try:
            while self._ws and not self._closed:
                msg = await self._ws.receive()
                if (t := msg.get("text")) is not None:
                    await self.push_text_frame(InputTextRawFrame(t))
        except (WebSocketDisconnect, ConnectionClosedError):
            return

# ── AUDIO WebSocket endpoint ---------------------------------------------
@app.websocket("/ws/audio")
async def ws_audio(ws: WebSocket):
    await ws.accept()
    transport = CafeTransport(
        websocket=ws,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            serializer=PCM(),
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(confidence=0.8, start_secs=0.1, stop_secs=0.2, min_volume=0.5)
            ),
        ),
    )
    task = build_pipeline(channel="audio", transport=transport)
    from pipecat.pipeline.runner import PipelineRunner
    try:
        await PipelineRunner(handle_sigint=False).run(task)
    finally:
        await ws.close()

# ── TEXT WebSocket endpoint ----------------------------------------------
@app.websocket("/ws/text")
async def ws_text(ws: WebSocket):
    await ws.accept()
    transport = TextOnlyTransport(
        websocket=ws,
        params=FastAPIWebsocketParams(
            audio_in_enabled=False,
            audio_out_enabled=False,
            serializer=TextSerializer(),
        ),
    )
    task = build_pipeline(channel="text", transport=transport)
    from pipecat.pipeline.runner import PipelineRunner
    try:
        await PipelineRunner(handle_sigint=False).run(task)
    finally:
        await ws.close()

# ── Uvicorn entrypoint -----------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        log_level="info",
    )

# hi
