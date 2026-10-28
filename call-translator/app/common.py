"""Shared translation constants (no third-party imports)."""

TARGETS = {"en": ("fr", "ar"), "fr": ("ar", "en")}
NAMES = {"en": "English", "fr": "French", "ar": "Arabic"}


class TranslationError(Exception):
    """User-facing translation failure."""
