"""U0.10a §5.3: the console watcher's own rules, without a browser."""

from types import SimpleNamespace
from typing import cast

from playwright.sync_api import ConsoleMessage, Error

from e2e.conftest import ConsoleWatch, is_policy_break

REFUSED = (
    "Refused to execute inline script because it violates the following "
    "Content Security Policy directive: \"script-src 'self'\"."
)
MISSING_ICON = "Failed to load resource: the server responded with a status of 404"


def test_a_csp_refusal_is_a_policy_break() -> None:
    assert is_policy_break(REFUSED)


def test_an_ordinary_console_error_is_not() -> None:
    assert not is_policy_break(MISSING_ICON)


def test_taking_the_problems_empties_the_watcher() -> None:
    watch = ConsoleWatch(problems=["one"])

    assert watch.take() == ["one"]
    assert watch.take() == []


def message(text: str) -> ConsoleMessage:
    """A console line as Playwright hands it over, without a browser."""
    return cast("ConsoleMessage", SimpleNamespace(text=text, page=None))


def test_the_watcher_keeps_a_refusal_and_lets_an_ordinary_error_go() -> None:
    watch = ConsoleWatch()

    watch.console(message(MISSING_ICON))
    watch.console(message(REFUSED))

    assert watch.take() == [f"None: {REFUSED}"]


def test_the_watcher_keeps_every_uncaught_script_error() -> None:
    watch = ConsoleWatch()

    watch.script_error(cast("Error", "ReferenceError: htmx is not defined"))

    assert watch.take() == [
        "uncaught script error: ReferenceError: htmx is not defined"
    ]
