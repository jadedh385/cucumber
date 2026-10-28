"""A translation that wraps every text in ⟦…⟧, for the U0.10a AC26 tests (§10.4).

Only English ships, so a text that skipped gettext reads the same as one that
went through it. Under this translation the first comes back bare and the
second wrapped.
"""

import gettext
from collections.abc import Iterator
from contextlib import contextmanager

from django.utils import translation
from django.utils.translation import trans_real


class Wrapping(gettext.NullTranslations):
    def gettext(self, message: str) -> str:
        return f"⟦{message}⟧"

    def ngettext(self, msgid1: str, msgid2: str, n: int) -> str:
        return f"⟦{msgid1 if n == 1 else msgid2}⟧"

    def pgettext(self, context: str, message: str) -> str:
        return f"⟦{message}⟧"

    def to_language(self) -> str:
        return "en"


def wrapped(text: str) -> str:
    return f"⟦{text}⟧"


@contextmanager
def wrapping_translation() -> Iterator[None]:
    """Inside, `gettext` and lazy texts come back wrapped in ⟦…⟧."""
    trans_real._active.value = Wrapping()  # type: ignore[attr-defined]  # noqa: SLF001
    try:
        yield
    finally:
        translation.deactivate()
