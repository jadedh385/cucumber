"""Browser-test set-up: Django's live server plus a phone-sized Chromium."""

import os
from typing import Any

import pytest

# Playwright's sync API runs an event loop, which makes Django refuse database
# calls as "unsafe from async". Browser tests only; never set in the app.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "1")

PHONE_VIEWPORT = {"width": 375, "height": 812}


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args: dict[str, Any]) -> dict[str, Any]:
    """Every browser test runs at phone width (U0.3 AC10)."""
    return {**browser_context_args, "viewport": PHONE_VIEWPORT}
