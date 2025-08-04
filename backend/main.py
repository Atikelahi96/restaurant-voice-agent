import os, sys, json, logging, uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from websockets.exceptions import ConnectionClosedError

from pipecat.transports.network.fastapi_websocket import (
    FastAPIWebsocketParams, FastAPIWebsocketTransport
)
from pipecat.audio.vad.silero import SileroVADAnalyzer, VADParams
from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame
from pipecat.serializers.base_serializer import FrameSerializer, FrameSerializerType

from backend.pipelines.factory import build_pipeline
from backend.routers import menu, orders
from backend.agent import chat as text_agent              # LangChain wrapper

# ── Windows selector loop (Ctrl-C fix) ---------------------------------------
if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("cafe-agent")

app = FastAPI(title="Sunrise Café AI – Phase-1")
app.include_router(menu.router,   prefix="/api")
app.include_router(orders.router, prefix="/api")

# ── PCM serializer (audio channel) ------------------------------------------
class PCM(FrameSerializer):
    @property
    def type(self): return FrameSerializerType.BINARY
    async def serialize(self, frame):                       # Pipecat → FE
        if isinstance(frame, OutputAudioRawFrame):
            return frame.audio
        # non-audio frames → JSON text for React
        return json.dumps(getattr(frame, "result", {"debug": str(frame)})).encode()
    async def deserialize(self, data: bytes):               # FE → Pipecat
        return InputAudioRawFrame(data, 16_000, 1)

# ── Robust transport (audio) -------------------------------------------------
class CafeTransport(FastAPIWebsocketTransport):
    async def _receive_messages(self):
        try:
            while self._ws and not self._closed:
                msg = await self._ws.receive()
                if (b := msg.get("bytes")):
                    await self.push_audio_frame(InputAudioRawFrame(b, 16_000, 1))
        except (WebSocketDisconnect, ConnectionClosedError):
            return

# ── /ws/audio  ---------------------------------------------------------------
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
                params=VADParams(confidence=0.8, start_secs=0.1,
                                 stop_secs=0.2, min_volume=0.5)
            ),
        ),
    )
    from pipecat.pipeline.runner import PipelineRunner
    task = build_pipeline(channel="audio", transport=transport)
    try:
        await PipelineRunner(handle_sigint=False).run(task)
    finally:
        await ws.close()

# ── /chat  (text channel – LangChain + Gemini) -------------------------------
from pydantic import BaseModel

class UserMsg(BaseModel):
    message: str

@app.post("/chat")
async def chat(msg: UserMsg):
    reply = text_agent(msg.message)
    return {"response": reply}

# ── run ----------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        log_level="info",
    )
