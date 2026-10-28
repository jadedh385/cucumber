"""U0.10a AC12: four taps in a second send one request (design §4.2).

On a slowed connection, with the POST held two seconds: Log in (a plain
form, `forms.js`) and the practice page's Save (an HTMX form, htmx's
`hx-sync` and `hx-disabled-elt`). The button shows it is sending; after
Back, and after a page comes back from the back-forward cache, it works
again. Headless Chromium may not use that cache, so the last test fires
the `pageshow` it would (§20 L9).

Nothing here changes an account or saves data, so it also runs on staging.
"""

import re
from collections.abc import Callable

import pytest
from playwright.sync_api import Page, expect

from cucumber.accounts.permissions import Role
from e2e.conftest import HeldPosts
from e2e.pages import (
    CHECKED,
    PRACTICE,
    middle_of,
    open_practice,
    pick_good_answers,
    save_button,
    sign_in_as,
    tap,
    tap_at,
)

pytestmark = pytest.mark.django_db(transaction=True)

LOGIN = "/accounts/login/"
TAPS = 4
TAP_GAP_MS = 150  # four taps inside a second
HOLD_MS = 2000
SIGNED_IN = "Signed in as"
CAME_BACK = (
    "window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))"
)


def tap_four_times(page: Page, button_name: str) -> None:
    finger = middle_of(page.get_by_role("button", name=button_name))
    for _ in range(TAPS):
        tap_at(page, finger)
        page.wait_for_timeout(TAP_GAP_MS)


def fill_login(page: Page, account: tuple[str, str]) -> None:
    page.get_by_label("Email").fill(account[0])
    page.get_by_label("Password").fill(account[1])


def open_login(page: Page, site_url: str, account: tuple[str, str]) -> None:
    page.goto(f"{site_url}{LOGIN}")
    fill_login(page, account)


# ------------------------------------------------------- a plain form
def test_four_taps_on_log_in_send_one_post(
    site_url: str,
    slow_network: Page,
    held_post: Callable[[str], HeldPosts],
    account: tuple[str, str],
) -> None:
    page = slow_network
    open_login(page, site_url, account)
    held = held_post(LOGIN)

    tap_four_times(page, "Log in")

    button = page.get_by_role("button", name="Log in")
    expect(button).to_have_attribute("aria-disabled", "true")
    expect(button).to_have_class(re.compile(r"\bis-sending\b"))
    expect(button).to_be_enabled()  # busy, not disabled: it still sends its name
    held.release_after(page, HOLD_MS)
    expect(page.get_by_text(SIGNED_IN).first).to_be_visible()
    assert held.sent == 1


def test_back_after_logging_in_leaves_log_in_working(
    site_url: str,
    page: Page,
    held_post: Callable[[str], HeldPosts],
    account: tuple[str, str],
) -> None:
    held = held_post(LOGIN)
    open_login(page, site_url, account)
    tap(page, page.get_by_role("button", name="Log in"))
    held.wait_until_sent(page, 1)
    held.release()
    expect(page.get_by_text(SIGNED_IN).first).to_be_visible()

    page.go_back()

    button = page.get_by_role("button", name="Log in")
    expect(button).not_to_have_attribute("aria-disabled", "true")
    fill_login(page, account)  # a reloaded page has lost what was typed
    tap(page, button)
    held.wait_until_sent(page, 2)
    held.release()
    expect(page.get_by_text(SIGNED_IN).first).to_be_visible()


def test_a_page_back_from_the_cache_sends_again(
    site_url: str,
    page: Page,
    held_post: Callable[[str], HeldPosts],
    account: tuple[str, str],
) -> None:
    open_login(page, site_url, account)
    held = held_post(LOGIN)
    button = page.get_by_role("button", name="Log in")
    finger = middle_of(button)
    tap_at(page, finger)
    expect(button).to_have_attribute("aria-disabled", "true")

    page.evaluate(CAME_BACK)

    expect(button).not_to_have_attribute("aria-disabled", "true")
    expect(page.locator("form[data-sending]")).to_have_count(0)
    tap_at(page, finger)
    held.wait_until_sent(page, 2)  # left unanswered: the browser dropped the first


# ------------------------------------------------------- an HTMX form
def test_four_taps_on_practice_save_send_one_post(
    site_url: str,
    slow_network: Page,
    held_post: Callable[[str], HeldPosts],
    account: tuple[str, str],
) -> None:
    page = slow_network
    sign_in_as(Role.ADMIN, page, site_url, account)
    open_practice(page, site_url)
    held = held_post(PRACTICE)

    tap_four_times(page, "Save")

    expect(save_button(page)).to_be_disabled()
    held.release_after(page, HOLD_MS)
    expect(page.get_by_text(CHECKED)).to_be_visible()
    expect(save_button(page)).to_be_enabled()
    assert held.sent == 1


def test_back_after_a_practice_save_leaves_save_working(
    site_url: str,
    page: Page,
    held_post: Callable[[str], HeldPosts],
    account: tuple[str, str],
) -> None:
    sign_in_as(Role.ADMIN, page, site_url, account)
    open_practice(page, site_url)
    held = held_post(PRACTICE)
    tap(page, save_button(page))
    held.wait_until_sent(page, 1)
    held.release()
    expect(page.get_by_text(CHECKED)).to_be_visible()
    page.goto(f"{site_url}/")

    page.go_back()

    expect(page).to_have_url(re.compile(re.escape(PRACTICE)))
    expect(save_button(page)).to_be_enabled()
    pick_good_answers(page)  # a reloaded page starts again
    tap(page, save_button(page))
    held.wait_until_sent(page, 2)
    held.release()
    expect(page.get_by_text(CHECKED)).to_be_visible()
