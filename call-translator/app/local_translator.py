"""Free, offline translation with Meta's NLLB-200 model running on CTranslate2.

Same interface as translator.Translator, so the server can use either.
The model is downloaded from Hugging Face on first start, then runs locally.
"""

import asyncio
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import ctranslate2
from huggingface_hub import hf_hub_download, snapshot_download
from tokenizers import Tokenizer

from . import config
from .transcriber import pick_device
from .common import TARGETS, TranslationError

log = logging.getLogger("local_translator")

# NLLB language codes. arb_Arab is Modern Standard Arabic.
NLLB_CODES = {"en": "eng_Latn", "fr": "fra_Latn", "ar": "arb_Arab"}
# All NLLB-200 models share one vocabulary; borrow the tokenizer if a repo lacks it.
TOKENIZER_REPO = "OpenNMT/nllb-200-distilled-1.3B-ct2-int8"
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


class LocalTranslator:
    def __init__(self, repo: str = config.NLLB_MODEL):
        self.repo = repo
        self.model = f"NLLB ({repo.split('/')[-1]})"
        self.ready = True  # no API key needed; load errors are reported per request
        self.load_error: str | None = None
        self.translator: ctranslate2.Translator | None = None
        self.tokenizer: Tokenizer | None = None
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nllb")

    def load(self) -> None:
        """Download (first run only) and load the model. Call from a worker thread."""
        try:
            path = Path(snapshot_download(self.repo))
            tok_file = path / "tokenizer.json"
            if not tok_file.exists():
                tok_file = Path(hf_hub_download(TOKENIZER_REPO, "tokenizer.json"))
            self.tokenizer = Tokenizer.from_file(str(tok_file))

            device, _ = pick_device()
            candidates = [(device, "int8_float16")] if device == "cuda" else []
            candidates.append(("cpu", "int8"))
            for device, compute in candidates:
                try:
                    self.translator = ctranslate2.Translator(str(path), device=device, compute_type=compute)
                    self._translate_sync("Hello.", "en")  # warm-up; also proves GPU libraries work
                    break
                except Exception as e:  # e.g. cuBLAS DLL missing -> CPU
                    if device == "cpu":
                        raise
                    log.warning("NLLB failed on %s (%s); falling back to CPU int8", device, e)
            self.model = f"NLLB {self.repo.split('/')[-1]} · {device}"
            log.info("Loaded %s on %s/%s", self.repo, device, compute)
        except Exception as e:  # noqa: BLE001 - surfaced to the UI
            log.exception("Failed to load translation model")
            self.load_error = f"Could not load translation model '{self.repo}': {e}"

    def _tokens(self, text: str, src: str) -> list[str]:
        ids = self.tokenizer.encode(text, add_special_tokens=False).ids
        return [NLLB_CODES[src]] + [self.tokenizer.id_to_token(i) for i in ids] + ["</s>"]

    def _detok(self, tokens: list[str]) -> str:
        ids = [self.tokenizer.token_to_id(t) for t in tokens]
        return self.tokenizer.decode([i for i in ids if i is not None], skip_special_tokens=True).strip()

    def _translate_sync(self, text: str, src: str) -> dict:
        sentences = [s for s in _SENTENCE_END.split(text.strip()) if s] or [text]
        targets = TARGETS[src]
        sources, prefixes = [], []
        for tgt in targets:
            for s in sentences:
                sources.append(self._tokens(s, src))
                prefixes.append([NLLB_CODES[tgt]])
        results = self.translator.translate_batch(
            sources,
            target_prefix=prefixes,
            beam_size=2,
            max_decoding_length=256,
            repetition_penalty=1.1,
        )
        out, i = {}, 0
        for tgt in targets:
            parts = []
            for _ in sentences:
                parts.append(self._detok(results[i].hypotheses[0][1:]))  # drop the language token
                i += 1
            out[tgt] = " ".join(p for p in parts if p)
        return {"source_lang": src, "translations": out}

    async def translate(self, text: str, whisper_lang: str, context: list[str] | None = None) -> dict:
        if self.load_error:
            raise TranslationError(self.load_error)
        if self.translator is None:
            raise TranslationError("Translation model is still loading…")
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(self.pool, self._translate_sync, text, whisper_lang)
        except Exception as e:  # noqa: BLE001
            log.exception("Local translation failed")
            raise TranslationError(f"Translation failed: {e}") from e
