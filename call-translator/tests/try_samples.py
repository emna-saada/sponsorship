"""Run the full pipeline (VAD -> Whisper -> translation) on audio files and print timings.

Usage (from the call-translator folder, venv active):
    python -m tests.try_samples english.wav french.mp3

Any format ffmpeg/PyAV can read works. Audio is fed in 250 ms chunks, the
same way the browser streams it.
"""

import asyncio
import sys
import time

import av
import numpy as np

from app import config
from app.local_translator import LocalTranslator
from app.segmenter import Segmenter
from app.transcriber import Transcriber
from app.translator import TranslationError, Translator


def decode_audio(path: str) -> np.ndarray:
    """Decode any audio file to 16 kHz mono float32."""
    resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
    chunks = []
    with av.open(path) as container:
        for frame in container.decode(audio=0):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):
            chunks.append(out.to_ndarray().reshape(-1))
    return np.concatenate(chunks).astype(np.float32) / 32768.0


async def main(paths: list[str]) -> None:
    t0 = time.perf_counter()
    stt = Transcriber()
    print(f"Whisper loaded on {stt.device} in {time.perf_counter() - t0:.1f}s")
    if config.TRANSLATOR == "claude":
        tr = Translator()
    else:
        t0 = time.perf_counter()
        tr = LocalTranslator()
        tr.load()
        if tr.load_error:
            print(tr.load_error)
            tr.ready = False
        else:
            print(f"{tr.model} loaded in {time.perf_counter() - t0:.1f}s")
    if not tr.ready:
        print("Translation unavailable - showing transcription only.")

    for path in paths:
        print(f"\n=== {path}")
        audio = decode_audio(path)
        seg = Segmenter()
        segments = []
        for i in range(0, len(audio), 4000):
            segments += seg.push(audio[i : i + 4000])
        segments += seg.flush()
        for s in segments:
            start = time.perf_counter()
            result = stt.transcribe(s.audio)
            stt_s = time.perf_counter() - start
            if result is None:
                print(f"  ({len(s.audio) / 16000:.1f}s segment ignored: silence/noise)")
                continue
            print(f"  [{result['lang'].upper()} p={result['lang_prob']:.2f}] {result['text']}   (STT {stt_s:.2f}s)")
            if tr.ready:
                try:
                    out = await tr.translate(result["text"], result["lang"])
                except TranslationError as e:
                    print(f"    ! {e}")
                    continue
                for lang, text in out["translations"].items():
                    print(f"    {lang}: {text}")
                print(f"    total after pause: {time.perf_counter() - start:.2f}s")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1:]))
