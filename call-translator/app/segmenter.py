"""Cuts a live 16 kHz audio stream into speech segments at natural pauses.

Uses the Silero VAD bundled with faster-whisper. Every incoming chunk, VAD is
run over the pending buffer (at most MAX_SEGMENT_S long, so this is cheap) and
a segment is emitted once speech is followed by SILENCE_MS of silence, or the
buffer reaches MAX_SEGMENT_S.
"""

from dataclasses import dataclass

import numpy as np
from faster_whisper.vad import VadOptions, get_speech_timestamps

from . import config

SR = config.SAMPLE_RATE
PAD = int(0.2 * SR)  # audio kept before/after speech so words aren't clipped


@dataclass
class Segment:
    audio: np.ndarray  # float32 mono 16 kHz
    speech_seconds: float


class Segmenter:
    def __init__(self, silence_ms: float = config.SILENCE_MS, max_seconds: float = config.MAX_SEGMENT_S):
        self.silence = int(silence_ms / 1000 * SR)
        self.max_len = int(max_seconds * SR)
        self.vad = VadOptions(
            threshold=config.VAD_THRESHOLD,
            min_speech_duration_ms=150,
            min_silence_duration_ms=int(silence_ms / 2),
            speech_pad_ms=0,
        )
        self.buf = np.zeros(0, dtype=np.float32)
        self.in_speech = False

    def reset(self) -> None:
        self.buf = np.zeros(0, dtype=np.float32)
        self.in_speech = False

    def push(self, chunk: np.ndarray) -> list[Segment]:
        """Add audio; return any finished segments."""
        self.buf = np.concatenate([self.buf, chunk.astype(np.float32)])
        out: list[Segment] = []
        while True:
            seg = self._try_cut()
            if seg is None:
                break
            out.append(seg)
        return out

    def flush(self) -> list[Segment]:
        """Emit whatever speech is pending (used on Stop)."""
        stamps = get_speech_timestamps(self.buf, self.vad) if len(self.buf) else []
        out = []
        if stamps:
            out.append(self._make(stamps, len(self.buf)))
        self.reset()
        return out

    def _make(self, stamps: list[dict], end: int) -> Segment:
        start = max(0, stamps[0]["start"] - PAD)
        stop = min(end, stamps[-1]["end"] + PAD)
        speech = sum(s["end"] - s["start"] for s in stamps) / SR
        return Segment(self.buf[start:stop].copy(), speech)

    def _try_cut(self) -> Segment | None:
        n = len(self.buf)
        if n < SR // 4:
            return None
        stamps = get_speech_timestamps(self.buf, self.vad)
        self.in_speech = bool(stamps) and (n - stamps[-1]["end"]) < self.silence

        if not stamps:
            # Only silence/noise: keep a short tail so a word onset isn't lost.
            if n > SR:
                self.buf = self.buf[-PAD:]
            return None

        last_end = stamps[-1]["end"]
        if n - last_end >= self.silence:
            seg = self._make(stamps, n)
            self.buf = self.buf[last_end:][-PAD:]
            self.in_speech = False
            return seg

        if n >= self.max_len:
            # Too long: cut at the longest internal pause if there is one, else hard cut.
            cut = n
            if len(stamps) > 1:
                gaps = [(stamps[i + 1]["start"] - stamps[i]["end"], i) for i in range(len(stamps) - 1)]
                _, i = max(gaps)
                cut = (stamps[i]["end"] + stamps[i + 1]["start"]) // 2
                stamps = stamps[: i + 1]
            else:
                stamps = [{"start": stamps[0]["start"], "end": n}]
            seg = self._make(stamps, cut)
            self.buf = self.buf[cut:]
            return seg

        # Drop leading silence so the buffer only grows with speech.
        if stamps[0]["start"] > 2 * PAD:
            self.buf = self.buf[stamps[0]["start"] - PAD :]
        return None
