"""Browser-test set-up: Django's live server plus a phone-sized Chromium."""

from collections.abc import Iterator
from typing import Any

import pytest

PHONE_VIEWPORT = {"width": 375, "height": 812}


@pytest.fixture(scope="session", autouse=True)
def allow_django_inside_playwright() -> Iterator[None]:
    """Playwright's sync API runs an event loop, which makes Django refuse
    database calls as "unsafe from async".

    Switched off only from the first browser test on (fixtures in this file
    apply to e2e/ only, which pytest runs last) and restored afterwards, so the
    other tests keep Django's guard. It has to cover the whole session because
    Playwright's event loop starts before any single test's database set-up.
    """
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("DJANGO_ALLOW_ASYNC_UNSAFE", "1")
        yield


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict[str, Any]) -> dict[str, Any]:
    """Every browser test runs at phone width (U0.3 AC10)."""
    return {**browser_context_args, "viewport": PHONE_VIEWPORT}
