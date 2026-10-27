"""FastAPI app: serves the UI and runs the live audio -> text -> translation pipeline.

WebSocket protocol (/ws)
  client -> server: binary frames of 16 kHz mono Int16 little-endian PCM,
                    text frames {"type": "start"} / {"type": "stop"}.
  server -> client: JSON {"type": "status" | "vad" | "segment" | "translation" | "error", ...}
"""

import asyncio
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .segmenter import Segment, Segmenter
from .transcriber import Transcriber
from .translator import TranslationError, Translator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("server")

STATIC = config.ROOT / "static"

# Whisper is CPU/GPU heavy and not meant for concurrent calls: one worker thread.
whisper_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="whisper")
state: dict = {"transcriber": None, "load_error": None, "ready": asyncio.Event()}
translator = Translator()


def _load_model() -> None:
    try:
        state["transcriber"] = Transcriber()
    except Exception as e:  # noqa: BLE001 - surfaced to the UI
        log.exception("Failed to load Whisper")
        state["load_error"] = f"Could not load Whisper model '{config.WHISPER_MODEL}': {e}"


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not translator.ready:
        log.warning("ANTHROPIC_API_KEY is not set - transcription will work, translation will not.")
    loop = asyncio.get_running_loop()
    task = loop.run_in_executor(whisper_pool, _load_model)
    task.add_done_callback(lambda _: state["ready"].set())
    yield


app = FastAPI(title="Live Call Translator", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


def _status() -> dict:
    t = state["transcriber"]
    return {
        "type": "status",
        "model_ready": t is not None,
        "loading": not state["ready"].is_set(),
        "load_error": state["load_error"],
        "whisper": config.WHISPER_MODEL,
        "device": t.device if t else None,
        "api_key": translator.ready,
        "claude_model": translator.model,
    }


@app.get("/api/status")
async def status():
    return _status()


class Session:
    """One browser connection."""

    def __init__(self, ws: WebSocket):
        self.ws = ws
        self.segmenter = Segmenter()
        self.queue: asyncio.Queue[Segment] = asyncio.Queue()
        self.context: list[str] = []
        self.next_id = 1
        self.speaking = False
        self.tasks: set[asyncio.Task] = set()

    async def send(self, msg: dict) -> None:
        try:
            await self.ws.send_text(json.dumps(msg, ensure_ascii=False))
        except Exception:  # noqa: BLE001 - socket closed
            pass

    async def on_audio(self, data: bytes) -> None:
        pcm = np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0
        for seg in self.segmenter.push(pcm):
            await self.queue.put(seg)
        if self.segmenter.in_speech != self.speaking:
            self.speaking = self.segmenter.in_speech
            await self.send({"type": "vad", "speaking": self.speaking})

    async def on_stop(self) -> None:
        for seg in self.segmenter.flush():
            await self.queue.put(seg)
        if self.speaking:
            self.speaking = False
            await self.send({"type": "vad", "speaking": False})

    async def worker(self) -> None:
        await state["ready"].wait()
        loop = asyncio.get_running_loop()
        while True:
            seg = await self.queue.get()
            t = state["transcriber"]
            if t is None:
                continue
            ended = time.perf_counter()
            await self.send({"type": "vad", "processing": True})
            try:
                result = await loop.run_in_executor(whisper_pool, t.transcribe, seg.audio)
            except Exception as e:  # noqa: BLE001
                log.exception("Transcription failed")
                await self.send({"type": "error", "message": f"Transcription failed: {e}"})
                continue
            finally:
                await self.send({"type": "vad", "processing": not self.queue.empty()})
            if result is None:
                continue
            seg_id = self.next_id
            self.next_id += 1
            stt_s = time.perf_counter() - ended
            log.info("#%d [%s %.2f] %.2fs STT: %s", seg_id, result["lang"], result["lang_prob"], stt_s, result["text"])
            await self.send({
                "type": "segment", "id": seg_id, "ts": datetime.now().strftime("%H:%M:%S"),
                "lang": result["lang"], "text": result["text"], "stt_ms": int(stt_s * 1000),
            })
            context = list(self.context)
            self.context = (self.context + [result["text"]])[-3:]
            # Translate concurrently so a slow API call never holds up the next transcription.
            task = asyncio.create_task(self.translate(seg_id, result, context, ended))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)

    async def translate(self, seg_id: int, result: dict, context: list[str], ended: float) -> None:
        try:
            tr = await translator.translate(result["text"], result["lang"], context)
        except TranslationError as e:
            await self.send({"type": "error", "id": seg_id, "message": str(e)})
            return
        except Exception as e:  # noqa: BLE001
            log.exception("Translation failed")
            await self.send({"type": "error", "id": seg_id, "message": f"Translation failed: {e}"})
            return
        total_ms = int((time.perf_counter() - ended) * 1000)
        log.info("#%d translated in %dms total: %s", seg_id, total_ms, tr["translations"])
        await self.send({"type": "translation", "id": seg_id, "total_ms": total_ms, **tr})


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    session = Session(ws)
    worker = asyncio.create_task(session.worker())
    await session.send(_status())
    if not state["ready"].is_set():
        async def announce_ready():
            await state["ready"].wait()
            await session.send(_status())
        session.tasks.add(asyncio.create_task(announce_ready()))
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("bytes"):
                await session.on_audio(msg["bytes"])
            elif msg.get("text"):
                cmd = json.loads(msg["text"]).get("type")
                if cmd == "start":
                    session.segmenter.reset()
                elif cmd == "stop":
                    await session.on_stop()
    except WebSocketDisconnect:
        pass
    finally:
        worker.cancel()
        for t in list(session.tasks):
            t.cancel()


def main() -> None:
    import uvicorn

    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")


if __name__ == "__main__":
    main()
