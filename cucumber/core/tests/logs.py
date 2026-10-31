"""What the container log would hold for a request (U0.10a §9.2, AC15–AC17).

The `django` logger doesn't propagate (settings.py), so pytest's `caplog`
never sees `django.*` records: a "no `django.request` line" check through
it would pass with no filter at all (architect H4). `logged` attaches a
handler, with the same filter as the console handler, to the `django`
logger and to the root logger (where `cucumber.*` lines go).
"""

import logging
from collections.abc import Iterator
from dataclasses import dataclass

import pytest

from cucumber.core.logs import OneLinePerRefusal


@dataclass(frozen=True)
class Line:
    """One line as it reaches the console handler."""

    logger: str
    message: str
    has_traceback: bool


def has_traceback(record: logging.LogRecord) -> bool:
    """A formatter prints `exc_info`, or the text an earlier handler cached
    from it in `exc_text`."""
    return record.exc_info is not None or bool(record.exc_text)


class Logged(logging.Handler):
    """Keeps every record the console handler would write, after its filter."""

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.addFilter(OneLinePerRefusal())
        self.kept: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.kept.append(record)

    def lines(self) -> list[Line]:
        return [
            Line(record.name, record.getMessage(), has_traceback(record))
            for record in self.kept
        ]

    def django(self) -> list[Line]:
        return [line for line in self.lines() if line.logger.startswith("django")]

    def cucumber(self) -> list[str]:
        return [
            line.message
            for line in self.lines()
            if line.logger == "cucumber" or line.logger.startswith("cucumber.")
        ]

    def text(self) -> str:
        """Every line in full, tracebacks included, as the log file would hold."""
        formatter = logging.Formatter("%(name)s: %(message)s")
        return "\n".join(formatter.format(record) for record in self.kept)


@pytest.fixture
def logged() -> Iterator[Logged]:
    handler = Logged()
    loggers = [logging.getLogger("django"), logging.getLogger()]
    for logger in loggers:
        logger.addHandler(handler)
    try:
        yield handler
    finally:
        for logger in loggers:
            logger.removeHandler(handler)
