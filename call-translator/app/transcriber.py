"""Local speech-to-text with faster-whisper, restricted to English / French."""

import logging
import re

import numpy as np
from faster_whisper import WhisperModel

from . import config

log = logging.getLogger("transcriber")

LANGS = ("en", "fr")

# Phrases Whisper invents on silence, music or line noise. Always dropped.
HALLUCINATIONS = {
    "thanks for watching", "thank you for watching", "please subscribe", "subscribe",
    "like and subscribe", "you", "merci d'avoir regardé", "merci d'avoir regardé cette vidéo",
    "sous titres réalisés par la communauté d'amara org", "sous titrage st' 501",
    "sous titrage société radio canada", "abonnez vous", "n'oubliez pas de vous abonner",
}
# Short phrases that are real in a call ("Merci", "Okay") but also common
# hallucinations: dropped only when Whisper wasn't confident there was speech.
WEAK_PHRASES = {
    "thank you", "thank you very much", "thanks", "bye", "bye bye", "so", "okay", "oh", "hmm",
    "merci", "merci beaucoup", "au revoir", "d'accord", "ok",
}
_PUNCT = re.compile(r"[^\w\s']+", re.UNICODE)


def _norm(text: str) -> str:
    return " ".join(_PUNCT.sub(" ", text.lower()).split())


def _pick_device() -> tuple[str, str]:
    want = config.WHISPER_DEVICE.lower()
    if want in ("auto", "cuda"):
        try:
            import ctranslate2

            if ctranslate2.get_cuda_device_count() > 0:
                return "cuda", "float16"
        except Exception:  # noqa: BLE001 - any CUDA probing failure means CPU
            pass
        if want == "cuda":
            log.warning("CUDA requested but not available; falling back to CPU")
    return "cpu", "int8"


class Transcriber:
    def __init__(self, model_name: str = config.WHISPER_MODEL):
        device, compute = _pick_device()
        try:
            self.model = WhisperModel(model_name, device=device, compute_type=compute)
        except Exception as e:  # e.g. CUDA present but cuDNN/cuBLAS DLLs missing
            if device == "cpu":
                raise
            log.warning("Could not load on %s (%s); using CPU int8", device, e)
            device, compute = "cpu", "int8"
            self.model = WhisperModel(model_name, device=device, compute_type=compute)
        self.device = f"{device}/{compute}"
        log.info("Whisper '%s' loaded on %s", model_name, self.device)
        # Warm up so the first real segment isn't slow.
        self.model.detect_language(np.zeros(config.SAMPLE_RATE, dtype=np.float32))

    def detect(self, audio: np.ndarray) -> tuple[str, float]:
        """Return the more likely of en/fr and its renormalised probability."""
        _, _, probs = self.model.detect_language(audio)
        p = {lang: prob for lang, prob in probs if lang in LANGS}
        en, fr = p.get("en", 0.0), p.get("fr", 0.0)
        total = (en + fr) or 1.0
        return ("en", en / total) if en >= fr else ("fr", fr / total)

    def transcribe(self, audio: np.ndarray) -> dict | None:
        """Transcribe one segment. Returns None for silence/noise/hallucinations."""
        lang, lang_prob = self.detect(audio)
        segments, _ = self.model.transcribe(
            audio,
            language=lang,
            beam_size=config.WHISPER_BEAM_SIZE,
            condition_on_previous_text=False,  # stops hallucination loops
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
            no_speech_threshold=0.6,
            log_prob_threshold=-1.0,
            compression_ratio_threshold=2.4,
        )
        parts = []
        confident = False
        for s in segments:
            if s.no_speech_prob > 0.6 and s.avg_logprob < -0.7:
                continue
            if s.avg_logprob < -1.2 or s.compression_ratio > 2.4:
                continue
            parts.append(s.text.strip())
            confident = confident or (s.no_speech_prob < 0.2 and s.avg_logprob > -0.6)
        text = _dedupe(" ".join(p for p in parts if p))
        if not is_meaningful(text, confident):
            return None
        return {"text": text, "lang": lang, "lang_prob": round(lang_prob, 3)}


def _dedupe(text: str) -> str:
    """Collapse Whisper's repeated-sentence loops ('Thank you. Thank you. Thank you.')."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    out: list[str] = []
    for s in sentences:
        if out and _norm(s) == _norm(out[-1]):
            continue
        out.append(s)
    return " ".join(out).strip()


def is_meaningful(text: str, confident: bool = False) -> bool:
    n = _norm(text)
    if not n or not any(ch.isalpha() for ch in n):
        return False
    if n in HALLUCINATIONS:
        return False
    return confident or n not in WEAK_PHRASES
