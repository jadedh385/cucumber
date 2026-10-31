"""Shared steps for the U0.10a browser tests (design §18).

Signing in as each role, the pages a role reaches from Home, the practice
form, and the 375 px checks (AC6, AC7).
"""

import re

import pytest
from playwright.sync_api import Locator, Page, ViewportSize, expect

from cucumber.accounts.permissions import Role
from cucumber.core.tests.stock import make_staff, restore_reference_rows
from e2e.conftest import E2E_PASSWORD

PHONE_WIDTH = 375
DESKTOP = ViewportSize(width=1280, height=800)
SMALLEST_TARGET = 44  # px, each way (AC7)
SMALLEST_TEXT = 16  # px in inputs, so iOS doesn't zoom (AC7)
TAPS_FROM_HOME = 2  # AC6

# Every role and none (AC5–AC7), by the name a test id shows.
ROLES: dict[str, Role | None] = {**{role.value: role for role in Role}, "none": None}

# What each role reaches in two taps from Home: every page it may open.
EVERYONE_S_PAGES = {"/", "/practice/", "/account/", "/accounts/password/"}
ADMIN_S_PAGES = EVERYONE_S_PAGES | {"/staff/", "/staff/new/", "/staff/<id>/"}

PRACTICE = "/practice/"
PRACTICE_FIELDS = ("stage", "medium", "container")
CHECKED = "Checked. Nothing was saved (practice page)."


def log_in(page: Page, site_url: str, email: str, password: str) -> None:
    page.goto(f"{site_url}/accounts/login/")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Log in").click()


def loaded(page: Page) -> Page:
    """The page, once it and its stylesheet have arrived. The text can show
    before the stylesheet does (G5, staging): until it arrives nothing hides
    the side menu and nothing sets the width, so a read of the layout would
    see a page no one sees."""
    page.wait_for_load_state("load")
    return page


def fits_the_phone(page: Page) -> None:
    width = loaded(page).evaluate("document.documentElement.scrollWidth")
    assert width <= PHONE_WIDTH, f"{page.url} scrolls sideways on a phone"


def open_from_menu(page: Page, name: str) -> None:
    """Tap a menu item. Home also has a tile for it, so the tap is on the
    menu's own link (§21.2)."""
    the_menu(page).get_by_role("link", name=name).click()


def log_out(page: Page) -> None:
    """Log out lives on the Account page (Q3 a), §21.2), not on Home."""
    open_from_menu(page, "Account")
    page.get_by_role("button", name="Log out").click()
    expect(page).to_have_url(re.compile(r"/accounts/login/"))


def pages_for(role: Role | None) -> set[str]:
    return ADMIN_S_PAGES if role is Role.ADMIN else EVERYONE_S_PAGES


def is_staging(site_url: str) -> bool:
    """The live server is http; a running site must be https (e2e/site.py)."""
    return site_url.startswith("https://")


def sign_in_as(
    role: Role | None, page: Page, site_url: str, account: tuple[str, str]
) -> None:
    """The Admin is `account` (staging's practice account there); any other
    role is a new local account, so its tests run locally only."""
    if role is Role.ADMIN:
        log_in(page, site_url, *account)
    else:
        if is_staging(site_url):
            pytest.skip("adds an account: runs against the local live server only")
        person = make_staff(f"e2e-{role or 'none'}", role, E2E_PASSWORD)
        log_in(page, site_url, person.username, E2E_PASSWORD)
    page.wait_for_url(re.compile(r"/$"))


# ------------------------------------------------------------- AC6 taps
def page_kind(path: str) -> str:
    """One name for every person's page: `/staff/<id>/`."""
    return re.sub(r"/staff/\d+/$", "/staff/<id>/", path)


def visible_links(page: Page) -> list[str]:
    """The paths of this site's links a person can see and tap."""
    hrefs: list[str] = page.eval_on_selector_all(
        "a[href]",
        "links => links.filter(a => a.checkVisibility())"
        ".map(a => new URL(a.href, location.href))"
        ".filter(url => url.origin === location.origin).map(url => url.pathname)",
    )
    return hrefs


def pages_within_two_taps(page: Page, site_url: str) -> dict[str, str]:
    """Each kind of page reached from Home in two taps, with one address."""
    reached = {"/": "/"}
    frontier = ["/"]
    for _ in range(TAPS_FROM_HOME):
        found: list[str] = []
        for path in frontier:
            page.goto(f"{site_url}{path}")
            for link in visible_links(page):
                if page_kind(link) not in reached:
                    reached[page_kind(link)] = link
                    found.append(link)
        frontier = found
    return reached


def the_menu(page: Page) -> Locator:
    """The menu as shown: the bottom bar on a phone, the side menu on a
    desktop (§21.2: the menu's links are the `<a>` inside `<nav>`)."""
    return loaded(page).locator("nav").filter(visible=True)


SCROLL_WAIT_MS = 2000
SCROLL_POLL_MS = 50


def scroll_down(page: Page, pixels: int) -> None:
    """Scroll as a thumb would, then wait until the page has moved.

    Polled from here: `wait_for_function` runs its text as script in the
    page, which the CSP refuses (no `unsafe-eval`, U0.10a §5).
    """
    page.mouse.wheel(0, pixels)
    for _ in range(SCROLL_WAIT_MS // SCROLL_POLL_MS):
        if page.evaluate("window.scrollY") > 0:
            return
        page.wait_for_timeout(SCROLL_POLL_MS)
    raise AssertionError("the page did not scroll")


# --------------------------------------------------------- AC7 the phone
def sideways_scroll(page: Page) -> int:
    width: int = page.evaluate("document.documentElement.scrollWidth")
    return width


# Buttons, menu items, the top bar's controls and the label row of a radio
# or check box (§20 L13) must be 44 x 44. A list link is stretched over its
# card (§7.6), so the card is measured and its middle must land on the link.
SMALL_TARGETS = """
size => {
  const small = [];
  const name = e => `${e.tagName.toLowerCase()} "${(e.innerText || e.value || "")
    .trim().slice(0, 30)}"`;
  const tooSmall = r => r.width < size || r.height < size;
  const targets = "button, input[type=submit], nav a, header a, header button,"
    + " label:has(input[type=radio]), label:has(input[type=checkbox])";
  for (const e of document.querySelectorAll(targets)) {
    if (e.checkVisibility() && tooSmall(e.getBoundingClientRect())) small.push(name(e));
  }
  for (const link of document.querySelectorAll("main table a")) {
    if (!link.checkVisibility()) continue;
    const card = link.closest("tr");
    card.scrollIntoView({block: "center"});
    const r = card.getBoundingClientRect();
    const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
    const onTheLink = hit && hit.closest("a") === link;
    if (tooSmall(r) || !onTheLink) small.push(name(link) + " card");
  }
  return small;
}
"""

SMALL_TEXT = """
size => [...document.querySelectorAll("select, textarea, input:not([type=hidden])"
    + ":not([type=radio]):not([type=checkbox])")]
  .filter(e => e.checkVisibility())
  .filter(e => parseFloat(getComputedStyle(e).fontSize) < size)
  .map(e => `${e.tagName.toLowerCase()} ${e.name}`)
"""


def small_targets(page: Page) -> list[str]:
    found: list[str] = page.evaluate(SMALL_TARGETS, SMALLEST_TARGET)
    return found


def small_text(page: Page) -> list[str]:
    found: list[str] = page.evaluate(SMALL_TEXT, SMALLEST_TEXT)
    return found


# -------------------------------------------------------- practice page
def open_practice(page: Page, site_url: str) -> None:
    """The practice form with a good answer picked in every field.

    Locally the reference lists are put back first: a committing test's
    flush empties them. Staging has its own.
    """
    if not is_staging(site_url):
        restore_reference_rows()
    page.goto(f"{site_url}{PRACTICE}")
    pick_good_answers(page)


def pick_good_answers(page: Page) -> None:
    """The first item of each list; the date stays today."""
    for name in PRACTICE_FIELDS:
        choice = page.locator(f'select[name="{name}"] option:not([value=""])').first
        page.locator(f'select[name="{name}"]').select_option(
            choice.get_attribute("value")
        )


def save_button(page: Page) -> Locator:
    return page.get_by_role("button", name="Save")


def middle_of(target: Locator) -> tuple[float, float]:
    """Where a finger goes, found before tapping: once a plain form is
    sending, Playwright's locators wait for the page load to finish."""
    target.scroll_into_view_if_needed()
    box = target.bounding_box()
    assert box is not None, "the button isn't on screen"
    return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2


def tap_at(page: Page, point: tuple[float, float]) -> None:
    """A finger on the screen: no waiting for the button to be ready, so a
    tap on a disabled button does nothing, as on a phone."""
    page.mouse.click(*point)


def tap(page: Page, target: Locator) -> None:
    tap_at(page, middle_of(target))
