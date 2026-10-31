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
from typing import Any

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
REPORT_WAIT_MS = 100
CAME_BACK_KEY = "F9"
SIGNED_IN = "Signed in as"
CAME_BACK = (
    "window.dispatchEvent(new PageTransitionEvent('pageshow', {persisted: true}))"
)
# Each change to the button and its form, sent to the test as it happens
# (Q-S2 a)). Once a plain form is sending, a locator or `page.evaluate`
# waits for the held navigation, so the test can't ask the page; the page
# tells the test.
REPORT_CHANGES = """
button => {
  const report = new MutationObserver(() => window.buttonChanged({
    ariaDisabled: button.getAttribute("aria-disabled"),
    classes: [...button.classList],
    disabled: button.disabled,
    formSending: button.form.hasAttribute("data-sending"),
  }));
  report.observe(button, {attributes: true});
  report.observe(button.form, {attributes: true});
}
"""


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


def watch_button(page: Page, button_name: str) -> list[dict[str, Any]]:
    """The button's states, newest last, as the page changes it."""
    seen: list[dict[str, Any]] = []

    def changed(state: dict[str, Any]) -> None:
        seen.append(state)

    page.expose_function("buttonChanged", changed)
    page.get_by_role("button", name=button_name).evaluate(REPORT_CHANGES)
    return seen


def newest(page: Page, seen: list[dict[str, Any]]) -> dict[str, Any]:
    page.wait_for_timeout(REPORT_WAIT_MS)  # Playwright hands reports over while waiting
    assert seen, "the button didn't change"
    return seen[-1]


def assert_shows_it_is_sending(page: Page, seen: list[dict[str, Any]]) -> None:
    """Busy, not disabled: it still sends its name (AC12)."""
    state = newest(page, seen)
    assert state["ariaDisabled"] == "true"
    assert "is-sending" in state["classes"]
    assert state["disabled"] is False


def ready_to_come_back(page: Page) -> None:
    """Pressing CAME_BACK_KEY fires the `pageshow` a page from the cache gets.

    Set before the tap: once the form is sending, the test can't run script
    in the page (not even through CDP), but a key press still gets through.
    """
    page.evaluate(
        "() => document.addEventListener('keydown', key => {"
        f" if (key.key === '{CAME_BACK_KEY}') {CAME_BACK}; }})"
    )


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
    seen = watch_button(page, "Log in")

    tap_four_times(page, "Log in")

    assert_shows_it_is_sending(page, seen)
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
    seen = watch_button(page, "Log in")
    ready_to_come_back(page)
    finger = middle_of(page.get_by_role("button", name="Log in"))
    tap_at(page, finger)
    assert_shows_it_is_sending(page, seen)

    page.keyboard.press(CAME_BACK_KEY)

    state = newest(page, seen)
    assert state["ariaDisabled"] != "true"
    assert not state["formSending"]
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
