"""Browser-test set-up: the site under test plus a phone-sized Chromium.

U0.10a §18 adds three tools: a console watcher on every browser test (a CSP
refusal or an uncaught script error fails it, §5.3), `slow_network` (the
vivo on poor Wi-Fi) and `held_post` (a POST held, answered or never answered,
for AC12–AC14).
"""

import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from django.contrib.auth.models import Group
from playwright.sync_api import (
    BrowserContext,
    ConsoleMessage,
    Error,
    Page,
    Route,
    expect,
)

from cucumber.accounts.permissions import Role
from cucumber.core.tests.stock import make_staff
from cucumber.core.tests.trail import restore_audit_rows
from e2e.site import access_headers, login_account, remote_site

PHONE_VIEWPORT = {"width": 375, "height": 812}
E2E_PASSWORD = "plum-orchid-42"  # noqa: S105 (a local test account)
ACTION_TIMEOUT_MS = 10_000
PAGE_LOAD_TIMEOUT_MS = 30_000
# `expect` has its own default (5 s); the slowed-network tests wait on it.
expect.set_options(timeout=ACTION_TIMEOUT_MS)

# Chromium writes every CSP refusal to the console in these words (§5.3).
POLICY_BREAK = "Content Security Policy"

# The vivo on poor Wi-Fi (§18): Chromium's own throttling, through CDP.
SLOW_LATENCY_MS = 400
SLOW_BYTES_PER_SECOND = 50_000

# The compiled stylesheet, whatever its hashed name (whitenoise's manifest).
STYLESHEET = "**/static/core/cucumber*.css"
STYLESHEET_DELAY_MS = 2000

# How long a test waits for a POST to reach a held route: 5 s at most.
SENT_CHECK_MS = 50
SENT_CHECKS = 100


def is_policy_break(text: str) -> bool:
    return POLICY_BREAK in text


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


@pytest.fixture
def context(context: BrowserContext) -> BrowserContext:
    """Add the Access service token (AC25) to requests for the site under test
    only, so no other host (a font, a redirect) ever sees it.

    An action (a tap, a read) waits 10 s at most, a page load 30 s: a test
    meeting a missing element fails in seconds, not half a minute each.
    """
    context.set_default_timeout(ACTION_TIMEOUT_MS)
    context.set_default_navigation_timeout(PAGE_LOAD_TIMEOUT_MS)
    site = remote_site(os.environ)
    headers = access_headers(os.environ)
    if site is None or not headers:
        return context

    def add_token(route: Route) -> None:
        route.continue_(headers={**route.request.headers, **headers})

    context.route(f"{site}/**", add_token)
    return context


@pytest.fixture
def site_url(request: pytest.FixtureRequest) -> str:
    """`E2E_SITE_URL` if set (see e2e/site.py), else Django's live server."""
    remote = remote_site(os.environ)
    if remote is not None:
        return remote
    url: str = request.getfixturevalue("live_server").url
    return url


@pytest.fixture
def is_remote() -> bool:
    return remote_site(os.environ) is not None


@pytest.fixture
def local_only(is_remote: bool) -> None:
    """For tests that add or change accounts: never on staging's practice data."""
    if is_remote:
        pytest.skip("changes accounts: runs against the local live server only")


@pytest.fixture
def account(request: pytest.FixtureRequest, is_remote: bool) -> tuple[str, str]:
    """An Admin to log in as: staging's practice account, or a fresh local one."""
    if is_remote:
        found = login_account(os.environ)
        if found is None:
            pytest.skip("set E2E_LOGIN_EMAIL and E2E_LOGIN_PASSWORD (see e2e/site.py)")
        return found
    request.getfixturevalue("transactional_db")
    for role in Role:  # a browser test's flush removes the seeded groups
        Group.objects.get_or_create(name=role)
    restore_audit_rows()  # and System, who makes set-up accounts (U0.7)
    owner = make_staff("jade", "admin", E2E_PASSWORD)
    return owner.username, E2E_PASSWORD


# ------------------------------------------------- U0.10a §5.3 the watcher
@dataclass
class ConsoleWatch:
    """What the browser said that a test must not ignore (§5.3)."""

    problems: list[str] = field(default_factory=list)

    def console(self, message: ConsoleMessage) -> None:
        if is_policy_break(message.text):
            self.problems.append(f"{message.page and message.page.url}: {message.text}")

    def script_error(self, error: Error) -> None:
        self.problems.append(f"uncaught script error: {error}")

    def take(self) -> list[str]:
        """The problems so far; the watcher starts again from none."""
        taken, self.problems = self.problems, []
        return taken


@pytest.fixture(autouse=True)
def console_watch(request: pytest.FixtureRequest) -> Iterator[ConsoleWatch]:
    """Every browser test fails on a CSP refusal or an uncaught script error,
    on every page it opens, locally and on staging (AC4). Tests that open no
    browser are left alone."""
    watch = ConsoleWatch()
    if "page" not in request.fixturenames and "context" not in request.fixturenames:
        yield watch
        return
    context: BrowserContext = request.getfixturevalue("context")
    context.on("console", watch.console)
    context.on("weberror", lambda web_error: watch.script_error(web_error.error))
    yield watch
    problems = watch.take()
    if problems:
        pytest.fail("the browser reported:\n" + "\n".join(problems))


# ---------------------------------------------- U0.10a §18 slow, held POSTs
@pytest.fixture
def slow_network(page: Page) -> Page:
    """The page on a slowed connection: 400 ms latency, 50 kB/s each way."""
    cdp = page.context.new_cdp_session(page)
    cdp.send("Network.enable")
    cdp.send(
        "Network.emulateNetworkConditions",
        {
            "offline": False,
            "latency": SLOW_LATENCY_MS,
            "downloadThroughput": SLOW_BYTES_PER_SECOND,
            "uploadThroughput": SLOW_BYTES_PER_SECOND,
        },
    )
    return page


@pytest.fixture
def slow_stylesheet(page: Page) -> Iterator[Page]:
    """The page with its stylesheet 2 s late, as over a slow link: the text
    arrives first and, for a moment, nothing hides the side menu (G5)."""
    headers = access_headers(os.environ)

    def late(route: Route) -> None:
        page.wait_for_timeout(STYLESHEET_DELAY_MS)
        route.continue_(headers={**route.request.headers, **headers})

    page.route(STYLESHEET, late)
    yield page
    page.unroute_all(behavior="ignoreErrors")


@dataclass
class HeldPosts:
    """The POSTs to one address, held until the test lets them go.

    A page route takes the place of the context route that adds the Access
    token on staging, so a held POST adds the headers itself (§20 L9). Other
    methods fall through to the context route.
    """

    headers: dict[str, str]
    waiting: list[Route] = field(default_factory=list)
    sent: int = 0  # POSTs the browser sent, held or let go

    def hold(self, route: Route) -> None:
        if route.request.method != "POST":
            route.fallback()
            return
        self.sent += 1
        self.waiting.append(route)

    def wait_until_sent(self, page: Page, count: int) -> None:
        """Playwright hands a route over only while the test waits on it."""
        for _ in range(SENT_CHECKS):
            if self.sent >= count:
                return
            page.wait_for_timeout(SENT_CHECK_MS)
        raise AssertionError(f"{self.sent} POST(s) sent, expected {count}")

    def release(self) -> None:
        """Let every held POST reach the site."""
        for route in self.take():
            route.continue_(headers={**route.request.headers, **self.headers})

    def release_after(self, page: Page, milliseconds: int) -> None:
        page.wait_for_timeout(milliseconds)
        self.release()

    def answer(self, status: int, headers: dict[str, str] | None = None) -> None:
        """Answer every held POST in the site's place; it never sees them."""
        for route in self.take():
            route.fulfill(status=status, headers=headers or {}, body="")

    def take(self) -> list[Route]:
        taken, self.waiting = self.waiting, []
        return taken


@pytest.fixture
def held_post(page: Page, site_url: str) -> Iterator[Callable[[str], HeldPosts]]:
    """`held_post("/practice/")`: from now on, POSTs there wait for the test.

    A POST never let go stays unanswered (AC13's "no answer").
    """

    def hold(path: str) -> HeldPosts:
        held = HeldPosts(headers=access_headers(os.environ))
        page.route(f"{site_url}{path}", held.hold)
        return held

    yield hold
    page.unroute_all(behavior="ignoreErrors")
