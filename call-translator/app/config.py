"""Settings loaded from environment / .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


# "local" = free offline NLLB-200 model; "claude" = Anthropic API (paid, needs a key)
TRANSLATOR = os.getenv("TRANSLATOR", "local").strip().lower()
NLLB_MODEL = os.getenv("NLLB_MODEL", "osa911/nllb-200-distilled-600M-ct2-int8")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-5-5")

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")  # small | medium | large-v3 ...
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "auto")  # auto | cuda | cpu
WHISPER_BEAM_SIZE = int(_float("WHISPER_BEAM_SIZE", 5))  # used only when greedy decoding looks unreliable

SAMPLE_RATE = 16000
SILENCE_MS = _float("SILENCE_MS", 600)  # pause that ends a segment
MAX_SEGMENT_S = min(_float("MAX_SEGMENT_S", 10), 28)  # Whisper handles up to 30 s at once
VAD_THRESHOLD = _float("VAD_THRESHOLD", 0.5)

HOST = "127.0.0.1"  # local only, never exposed to the network
PORT = int(_float("PORT", 8000))
