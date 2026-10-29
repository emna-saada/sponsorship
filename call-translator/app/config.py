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
# "auto" = NLLB 1.3B on a GPU (more accurate), 600M on CPU (faster)
NLLB_MODEL = os.getenv("NLLB_MODEL", "auto")
NLLB_GPU = "OpenNMT/nllb-200-distilled-1.3B-ct2-int8"
NLLB_CPU = "osa911/nllb-200-distilled-600M-ct2-int8"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-5-5")

# "auto" = large-v3-turbo on a GPU (much more accurate), small on CPU (fast enough live)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "auto")
WHISPER_GPU = "large-v3-turbo"
WHISPER_CPU = "small"
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "auto")  # auto | cuda | cpu
WHISPER_BEAM_SIZE = int(_float("WHISPER_BEAM_SIZE", 5))  # used only when greedy decoding looks unreliable

# CPU threads per model (Whisper and NLLB each); default: half the logical cores, min 4
CPU_THREADS = int(_float("CPU_THREADS", max(4, (os.cpu_count() or 4) // 2)))

SAMPLE_RATE = 16000
SILENCE_MS = _float("SILENCE_MS", 600)  # pause that ends a segment
MAX_SEGMENT_S = min(_float("MAX_SEGMENT_S", 10), 28)  # Whisper handles up to 30 s at once
VAD_THRESHOLD = _float("VAD_THRESHOLD", 0.5)

HOST = "127.0.0.1"  # local only, never exposed to the network
PORT = int(_float("PORT", 8000))
