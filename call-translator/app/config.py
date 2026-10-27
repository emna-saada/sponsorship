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


ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-5-5")

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")  # small | medium | large-v3 ...
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "auto")  # auto | cuda | cpu
WHISPER_BEAM_SIZE = int(_float("WHISPER_BEAM_SIZE", 5))

SAMPLE_RATE = 16000
SILENCE_MS = _float("SILENCE_MS", 600)  # pause that ends a segment
MAX_SEGMENT_S = _float("MAX_SEGMENT_S", 10)
VAD_THRESHOLD = _float("VAD_THRESHOLD", 0.5)

HOST = "127.0.0.1"  # local only, never exposed to the network
PORT = int(_float("PORT", 8000))
