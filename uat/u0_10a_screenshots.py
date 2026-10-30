"""U0.10a G5: phone-width and desktop screenshots of the pages and the error pages.

Uses the E2E suite's own browser (Playwright's Chromium) and its settings
(`e2e/site.py`), so the same four variables point it at staging:

    read -rs E2E_ACCESS_CLIENT_ID; read -rs E2E_ACCESS_CLIENT_SECRET
    read -rs E2E_LOGIN_PASSWORD
    export E2E_SITE_URL=https://cucumber-staging.southeastcanopy.com \\
        E2E_ACCESS_CLIENT_ID E2E_ACCESS_CLIENT_SECRET E2E_LOGIN_PASSWORD \\
        E2E_LOGIN_EMAIL=<the practice account>
    PYTHONPATH=. uv run python uat/u0_10a_screenshots.py \\
        docs/roadmap/units/u0.10a-g5-screenshots

It changes nothing: it logs in, opens pages and takes pictures. The 403 page needs
a signed-in person who isn't an Admin: set `E2E_TECH_EMAIL` and `E2E_TECH_PASSWORD`
for one (staging has the U0.8 sandbox Tech), or the 403 pictures are skipped. The
Busy page can't be made on demand: run with `--busy` while the lock in
docs/roadmap/units/u0.10a-g5-verify.md is held (it waits for Enter).
"""

import argparse
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path

from playwright.sync_api import Browser, BrowserContext, Page, Route, sync_playwright

from e2e.site import access_headers, login_account

SIZES = {"375": (375, 812), "1280": (1280, 800)}
LOAD_WAIT_MS = 30_000
LOCAL_HOSTS = ("http://127.0.0.1", "http://localhost")  # only to try the script out
TECH_EMAIL = "E2E_TECH_EMAIL"
TECH_PASSWORD = "E2E_TECH_PASSWORD"  # noqa: S105 (a variable name)
STAFF_PERSON = re.compile(r"^/staff/\d+/$")
# A form posted with no token: Django answers with the CSRF page.
POST_WITH_NO_CSRF = """() => {
  const form = document.createElement('form');
  form.method = 'post';
  form.action = '/accounts/password/';
  document.body.appendChild(form);
  form.submit();
}"""


def site_address(environ: Mapping[str, str]) -> str:
    url = environ.get("E2E_SITE_URL", "").strip().rstrip("/")
    if not url.startswith(("https://", *LOCAL_HOSTS)):
        raise SystemExit("Set E2E_SITE_URL to the https:// address of the site")
    return url


def new_context(browser: Browser, site: str, size: tuple[int, int]) -> BrowserContext:
    context = browser.new_context(viewport={"width": size[0], "height": size[1]})
    context.set_default_timeout(LOAD_WAIT_MS)
    headers = access_headers(os.environ)
    if headers:

        def add_token(route: Route) -> None:
            route.continue_(headers={**route.request.headers, **headers})

        context.route(f"{site}/**", add_token)
    return context


def log_in(page: Page, site: str, email: str, password: str) -> None:
    page.goto(f"{site}/accounts/login/")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url(re.compile(r"/$"))


def shoot(page: Page, folder: Path, width: str, name: str) -> None:
    page.wait_for_load_state("networkidle")
    path = folder / f"{name}-{width}.png"
    page.screenshot(path=str(path), full_page=True)
    sys.stdout.write(f"  {path}\n")


def visit(
    page: Page, site: str, path: str, folder: Path, width: str, name: str
) -> None:
    page.goto(f"{site}{path}")
    shoot(page, folder, width, name)


def first_person_path(page: Page) -> str | None:
    for link in page.locator("a[href^='/staff/']").all():
        href = link.get_attribute("href") or ""
        if STAFF_PERSON.match(href):
            return href
    return None


def admin_pages(page: Page, site: str, folder: Path, width: str) -> None:
    visit(page, site, "/", folder, width, "home")
    visit(page, site, "/account/", folder, width, "account")
    visit(page, site, "/accounts/password/", folder, width, "password")
    visit(page, site, "/practice/", folder, width, "practice")
    visit(page, site, "/staff/", folder, width, "staff-list")
    person = first_person_path(page)
    if person:
        visit(page, site, person, folder, width, "staff-detail")
    visit(page, site, "/staff/new/", folder, width, "staff-add")
    visit(page, site, "/no-such-page/", folder, width, "error-404")
    page.goto(f"{site}/accounts/password/")
    page.evaluate(POST_WITH_NO_CSRF)
    page.wait_for_url(re.compile(r"/accounts/password/"))
    shoot(page, folder, width, "error-csrf")


def refused_page(
    browser: Browser, site: str, size: tuple[int, int], folder: Path, width: str
) -> None:
    email, password = os.environ.get(TECH_EMAIL), os.environ.get(TECH_PASSWORD)
    if not (email and password):
        sys.stdout.write(f"  (no {TECH_EMAIL}: the 403 page is skipped)\n")
        return
    context = new_context(browser, site, size)
    page = context.new_page()
    log_in(page, site, email, password)
    visit(page, site, "/staff/", folder, width, "error-403")
    context.close()


def busy_page(page: Page, site: str, folder: Path, width: str) -> None:
    input("Start the lock now (see the G5 note), then press Enter: ")
    page.goto(f"{site}/staff/")
    shoot(page, folder, width, "error-busy")


def take_all(folder: Path, with_busy: bool) -> None:
    site = site_address(os.environ)
    account = login_account(os.environ)
    if account is None:
        raise SystemExit("Set E2E_LOGIN_EMAIL and E2E_LOGIN_PASSWORD")
    folder.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        for width, size in SIZES.items():
            sys.stdout.write(f"{width} px\n")
            context = new_context(browser, site, size)
            page = context.new_page()
            visit(page, site, "/accounts/login/", folder, width, "login")
            log_in(page, site, *account)
            admin_pages(page, site, folder, width)
            if with_busy:
                page.goto(f"{site}/staff/")
                busy_page(page, site, folder, width)
            context.close()
            refused_page(browser, site, size, folder, width)
        browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("folder", type=Path)
    parser.add_argument("--busy", action="store_true", help="also the Busy page")
    arguments = parser.parse_args()
    take_all(arguments.folder, arguments.busy)


if __name__ == "__main__":
    main()
