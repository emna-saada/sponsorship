"""Run the full pipeline (VAD -> Whisper -> Claude) on audio files and print timings.

Usage (from the call-translator folder, venv active):
    python -m tests.try_samples english.wav french.mp3

Any format ffmpeg/PyAV can read works. Audio is fed in 250 ms chunks, the
same way the browser streams it.
"""

import asyncio
import sys
import time

from faster_whisper import decode_audio

from app.segmenter import Segmenter
from app.transcriber import Transcriber
from app.translator import TranslationError, Translator


async def main(paths: list[str]) -> None:
    t0 = time.perf_counter()
    stt = Transcriber()
    print(f"Whisper loaded on {stt.device} in {time.perf_counter() - t0:.1f}s")
    tr = Translator()
    if not tr.ready:
        print("ANTHROPIC_API_KEY not set - showing transcription only.")

    for path in paths:
        print(f"\n=== {path}")
        audio = decode_audio(path, sampling_rate=16000)
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
