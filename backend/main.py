# backend/main.py
import os, sys, json, logging, uvicorn, asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from websockets.exceptions import ConnectionClosedError

from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.audio.vad.silero import SileroVADAnalyzer, VADParams
from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame
from pipecat.serializers.base_serializer import FrameSerializer, FrameSerializerType

from backend.pipelines.factory import build_pipeline
from backend.routers import menu, orders

# ─── Windows event-loop quirk ─────────────────────────────────────────
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ─── dotenv + logging ────────────────────────────────────────────────
load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cafe-agent")

# ─── FastAPI + routers ───────────────────────────────────────────────
app = FastAPI(title="Sunrise Café AI – Phase 1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)
app.include_router(menu.router,   prefix="/api")
app.include_router(orders.router, prefix="/api")

# ─── PCM + JSON serializer ───────────────────────────────────────────
class AudioJsonSerializer(FrameSerializer):
    """Return raw PCM; forward any `.result` dict as JSON text."""
    @property
    def type(self) -> FrameSerializerType:
        return FrameSerializerType.BINARY

    async def serialize(self, frame):
        #log.info("SERIALIZER FRAME: %s", type(frame))
        if hasattr(frame, "result"):
            payload = json.loads(json.dumps(frame.result, default=str))
            #log.info("WS-JSON → %s", payload)
            await self._transport.websocket.send_text(json.dumps(payload))
        if isinstance(frame, OutputAudioRawFrame):
            return frame.audio
        return None

    async def deserialize(self, data: bytes):
        return InputAudioRawFrame(data, 16_000, 1)

# ─── Transport ───────────────────────────────────────────────────────
class CafeTransport(FastAPIWebsocketTransport):
    """Receives raw PCM; emits PCM + JSON."""
    async def _receive_messages(self):
        try:
            while self._ws and not self._closed:
                msg = await self._ws.receive()
                if (b := msg.get("bytes")):
                    await self.push_audio_frame(InputAudioRawFrame(b, 16_000, 1))
        except (WebSocketDisconnect, ConnectionClosedError):
            return

# ─── /ws/audio endpoint ──────────────────────────────────────────────
@app.websocket("/ws/audio")
async def ws_audio(ws: WebSocket):
    await ws.accept()

   

    serializer = AudioJsonSerializer()
    transport  = CafeTransport(
        websocket=ws,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            serializer=serializer,
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(confidence=0.8,
                                 start_secs=0.1,
                                 stop_secs=0.2,
                                 min_volume=0.5)
            ),
        ),
    )

    # Cross-link serializer ↔ transport
    serializer._transport = transport
    transport._serializer = serializer

    # Give llm_tools a handle so it can shortcut JSON to UI
    import backend.utils.llm_tools as llm_tools
    llm_tools._WS = ws

    # Build and run the pipeline
    task = build_pipeline(channel="audio", transport=transport)
    from pipecat.pipeline.runner import PipelineRunner
    try:
        await PipelineRunner(handle_sigint=False).run(task)
    finally:
        try:
            await ws.close()
        except RuntimeError:
            pass

# ─── uvicorn entry-point ─────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        log_level="info",
    )
