"""Translation via the Claude API (one request per speech segment)."""

import logging
from typing import Literal

import anthropic
from pydantic import BaseModel

from . import config
from .common import TARGETS, TranslationError

log = logging.getLogger("translator")

SYSTEM = """You are a live interpreter for a phone call. Each message is one \
transcribed utterance (from speech recognition, so it may lack punctuation or \
contain small recognition errors). Speakers use English or French.

Return JSON with:
- source_lang: "en" or "fr", the language of the utterance (the speech \
recognizer's guess is given but may be wrong).
- translations: the utterance rendered in all three languages:
  - "en": English, "fr": French, "ar": Modern Standard Arabic (فصحى).
  For the source language, return the utterance itself, lightly cleaned up \
(punctuation, obvious recognition errors), without changing its meaning.

Translate faithfully and naturally, as an interpreter would speak it: keep \
names, numbers, dates, addresses and amounts exact; keep the speaker's tone \
and register; don't add explanations, notes or quotation marks. Earlier \
utterances may be given for context only - translate just the current one."""


class Translations(BaseModel):
    en: str
    fr: str
    ar: str


class TranslationResult(BaseModel):
    source_lang: Literal["en", "fr"]
    translations: Translations


class Translator:
    def __init__(self, api_key: str = config.ANTHROPIC_API_KEY, model: str = config.CLAUDE_MODEL):
        self.model = model
        self.client = anthropic.AsyncAnthropic(api_key=api_key, timeout=20.0, max_retries=2) if api_key else None

    @property
    def ready(self) -> bool:
        return self.client is not None

    async def translate(self, text: str, whisper_lang: str, context: list[str] | None = None) -> dict:
        if not self.client:
            raise TranslationError("Missing API key: set ANTHROPIC_API_KEY in the .env file and restart.")

        prompt = ""
        if context:
            prompt += "Earlier in the call (context only):\n" + "\n".join(f"- {c}" for c in context[-3:]) + "\n\n"
        prompt += f"Speech recognizer language guess: {whisper_lang}\nUtterance to translate:\n{text}"

        try:
            resp = await self.client.messages.parse(
                model=self.model,
                max_tokens=2048,
                system=SYSTEM,
                output_config={"effort": "low"},  # latency matters more than deep reasoning here
                output_format=TranslationResult,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.AuthenticationError as e:
            raise TranslationError("Anthropic API key was rejected - check ANTHROPIC_API_KEY in .env.") from e
        except anthropic.PermissionDeniedError as e:
            raise TranslationError(f"API permission denied: {e.message}") from e
        except anthropic.NotFoundError as e:
            raise TranslationError(f"Model '{self.model}' not found - check CLAUDE_MODEL in .env.") from e
        except anthropic.RateLimitError as e:
            raise TranslationError("API rate limit reached - wait a moment and keep talking.") from e
        except anthropic.APITimeoutError as e:
            raise TranslationError("Translation request timed out.") from e
        except anthropic.APIConnectionError as e:
            raise TranslationError("Could not reach the Anthropic API - check your internet connection.") from e
        except anthropic.APIStatusError as e:
            raise TranslationError(f"API error {e.status_code}: {e.message}") from e

        if resp.stop_reason == "refusal":
            raise TranslationError("The model declined to translate this segment.")
        result = resp.parsed_output
        if result is None:
            raise TranslationError(f"Unexpected API response (stop_reason={resp.stop_reason}).")

        src = result.source_lang
        all_t = result.translations.model_dump()
        return {
            "source_lang": src,
            "translations": {lang: all_t[lang] for lang in TARGETS[src]},
        }
