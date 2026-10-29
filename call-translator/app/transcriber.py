"""Local speech-to-text with faster-whisper, restricted to English / French."""

import logging
import re

import numpy as np
from faster_whisper import WhisperModel
from faster_whisper.audio import pad_or_trim
from faster_whisper.tokenizer import Tokenizer
from faster_whisper.transcribe import get_compression_ratio, get_suppressed_tokens

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


def pick_device() -> tuple[str, str]:
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


def _candidates(want: str, gpu_model: str, cpu_model: str) -> list[tuple[str, str]]:
    """(model, device) pairs to try in order: best quality first, CPU last."""
    device, _ = pick_device()
    gpu = device == "cuda"
    if want != "auto":
        return [(want, "cuda"), (want, "cpu")] if gpu else [(want, "cpu")]
    if gpu:
        return [(gpu_model, "cuda"), (cpu_model, "cuda"), (cpu_model, "cpu")]
    return [(cpu_model, "cpu")]


class Transcriber:
    def __init__(self, model_name: str = config.WHISPER_MODEL):
        for name, device in _candidates(model_name, config.WHISPER_GPU, config.WHISPER_CPU):
            compute = "int8_float16" if device == "cuda" else "int8"
            try:
                self._load(name, device, compute)
                # Warm up (also proves the GPU libraries and memory actually work).
                self.transcribe(np.zeros(config.SAMPLE_RATE, dtype=np.float32))
                break
            except Exception as e:
                if device == "cpu":
                    raise
                log.warning("Whisper '%s' failed on %s (%s); trying a lighter option", name, device, e)
        log.info("Whisper '%s' ready on %s", self.name, self.device)

    def _load(self, model_name: str, device: str, compute: str) -> None:
        self.model = WhisperModel(model_name, device=device, compute_type=compute, cpu_threads=config.CPU_THREADS)
        self.name = model_name
        self.on_gpu = device == "cuda"
        self.device = f"{device}/{compute}"
        self.tokenizers = {
            lang: Tokenizer(self.model.hf_tokenizer, multilingual=True, task="transcribe", language=lang)
            for lang in LANGS
        }
        self.suppress = {lang: list(get_suppressed_tokens(t, [-1])) for lang, t in self.tokenizers.items()}

    def _decode(self, encoder_output, lang: str, beam_size: int) -> tuple[str, float, float]:
        tok = self.tokenizers[lang]
        result = self.model.model.generate(
            encoder_output,
            [tok.sot_sequence + [tok.no_timestamps]],
            beam_size=beam_size,
            length_penalty=1,
            max_length=self.model.max_length,
            return_scores=True,
            return_no_speech_prob=True,
            suppress_blank=True,
            suppress_tokens=self.suppress[lang],
        )[0]
        tokens = result.sequences_ids[0]
        avg_logprob = result.scores[0] * len(tokens) / (len(tokens) + 1)
        return tok.decode(tokens).strip(), avg_logprob, result.no_speech_prob

    def transcribe(self, audio: np.ndarray) -> dict | None:
        """Transcribe one segment (<= 30 s). Returns None for silence/noise/hallucinations.

        The audio is encoded once; language detection and decoding both reuse
        that encoder output, which is ~40% faster than faster-whisper's
        transcribe() with a separate detect_language() pass.
        """
        features = self.model.feature_extractor(audio)
        encoder_output = self.model.encode(pad_or_trim(features))

        probs = {tok[2:-2]: p for tok, p in self.model.model.detect_language(encoder_output)[0]}
        en, fr = probs.get("en", 0.0), probs.get("fr", 0.0)
        lang = "en" if en >= fr else "fr"
        lang_prob = max(en, fr) / ((en + fr) or 1.0)

        # GPU: beam search always (cheap there, more accurate).
        # CPU: greedy first; beam search only if the result looks unreliable.
        text, avg_logprob, no_speech = self._decode(encoder_output, lang, config.WHISPER_BEAM_SIZE if self.on_gpu else 1)
        if not self.on_gpu and (get_compression_ratio(text) > 2.4 or avg_logprob < -1.0):
            text, avg_logprob, no_speech = self._decode(encoder_output, lang, config.WHISPER_BEAM_SIZE)

        if no_speech > 0.6 and avg_logprob < -0.7:
            return None
        if avg_logprob < -1.2 or get_compression_ratio(text) > 2.4:
            return None
        confident = no_speech < 0.2 and avg_logprob > -0.6
        text = _dedupe(text)
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
