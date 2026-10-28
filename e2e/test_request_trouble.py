"""U0.10a AC13, AC14: when a save goes wrong, the words say how (design §4.3).

On the practice page's HTMX Save, the banner `#request-trouble` shows one
message, and Save works again every time. The answers are made by the test
(`held_post`), so the site never sees these POSTs; they run on staging too,
except AC13, whose shortened timeout is a setting of the local live server.
"""

import json
from collections.abc import Callable, Iterator

import pytest
from django.test import override_settings
from playwright.sync_api import Page, expect

from cucumber.accounts.permissions import Role
from e2e.conftest import HeldPosts
from e2e.pages import CHECKED, PRACTICE, open_practice, save_button, sign_in_as, tap

pytestmark = pytest.mark.django_db(transaction=True)

TROUBLE = "#request-trouble"
NOT_CONFIRMED = (
    "Not confirmed: check your signal and tap Save again. "
    "If it was saved, you'll see Already saved."
)
OFFLINE = "You're offline or the signal dropped. Nothing was sent."
SERVER_ERROR = (
    "Something went wrong on our side. Tap Save again; "
    "if it keeps happening, tell the Owner."
)
BUSY = "Busy, please try again."
STALE_PAGE = "This page was open too long. Reload it and try again."
NO_ACCESS = "You don't have access to this page."
STALE_HEADER = {"Cucumber-Trouble": "stale-page"}
HTMX_TIMEOUT_MS = 20_000  # §8.3
SHORT_TIMEOUT_MS = 1_000


@pytest.fixture
def on_practice(site_url: str, page: Page, account: tuple[str, str]) -> Page:
    sign_in_as(Role.ADMIN, page, site_url, account)
    open_practice(page, site_url)
    return page


@pytest.fixture
def short_timeout(local_only: None) -> Iterator[None]:
    with override_settings(HTMX_TIMEOUT_MS=SHORT_TIMEOUT_MS):
        yield


def save_works_again(page: Page, held: HeldPosts) -> None:
    """The button is back, and a second tap sends a second POST."""
    expect(save_button(page)).to_be_enabled()
    tap(page, save_button(page))
    held.wait_until_sent(page, 2)


# ------------------------------------------------------------- AC13
def test_a_normal_page_waits_twenty_seconds(on_practice: Page) -> None:
    config = on_practice.locator('meta[name="htmx-config"]').get_attribute("content")

    assert config is not None
    assert json.loads(config)["timeout"] == HTMX_TIMEOUT_MS


def test_no_answer_says_not_confirmed_never_not_saved(
    short_timeout: None, on_practice: Page, held_post: Callable[[str], HeldPosts]
) -> None:
    page = on_practice
    held = held_post(PRACTICE)  # never let go: no answer

    tap(page, save_button(page))

    expect(page.locator(TROUBLE)).to_contain_text(NOT_CONFIRMED)
    expect(page.locator("body")).not_to_contain_text("not saved", ignore_case=True)
    save_works_again(page, held)


# ------------------------------------------------------------- AC14
def test_no_connection_says_offline(on_practice: Page) -> None:
    page = on_practice
    page.context.set_offline(True)

    tap(page, save_button(page))

    expect(page.locator(TROUBLE)).to_contain_text(OFFLINE)
    page.context.set_offline(False)
    tap(page, save_button(page))
    expect(page.get_by_text(CHECKED)).to_be_visible()
    expect(page.locator(TROUBLE)).not_to_contain_text(OFFLINE)


@pytest.mark.parametrize(
    ("status", "headers", "words"),
    [
        (500, {}, SERVER_ERROR),
        (503, {}, BUSY),
        (403, STALE_HEADER, STALE_PAGE),
        (403, {}, NO_ACCESS),
    ],
    ids=["server-error", "busy", "stale-page", "no-access"],
)
def test_a_failed_answer_says_which_failure(
    status: int,
    headers: dict[str, str],
    words: str,
    on_practice: Page,
    held_post: Callable[[str], HeldPosts],
) -> None:
    page = on_practice
    held = held_post(PRACTICE)
    tap(page, save_button(page))
    held.wait_until_sent(page, 1)

    held.answer(status, headers)

    expect(page.locator(TROUBLE)).to_contain_text(words)
    save_works_again(page, held)


def test_the_stale_page_words_offer_reload(
    on_practice: Page, held_post: Callable[[str], HeldPosts]
) -> None:
    page = on_practice
    held = held_post(PRACTICE)
    tap(page, save_button(page))
    held.wait_until_sent(page, 1)

    held.answer(403, STALE_HEADER)

    expect(page.locator(TROUBLE).get_by_role("link", name="Reload")).to_be_visible()
