"""Where the browser tests point (AC25).

By default they run against Django's live server, started for the test run.
Set `E2E_SITE_URL` to run them against a site that is already running, for
example staging through its tunnel:

    E2E_SITE_URL=https://cucumber-staging.… uv run pytest e2e --no-cov

Cloudflare Access stands in front of staging and asks for an emailed code,
which a test browser can't read. An Access *service token* lets it through:
set `E2E_ACCESS_CLIENT_ID` and `E2E_ACCESS_CLIENT_SECRET` (in Bitwarden) and
every request carries them as headers.

Cucumber's own login (U0.5) then needs an account on that site: set
`E2E_LOGIN_EMAIL` and `E2E_LOGIN_PASSWORD` for staging's practice account
(in Bitwarden, kept by the Owner like the service token). Locally each test
makes its own accounts.
"""

from collections.abc import Mapping

SITE_URL = "E2E_SITE_URL"
ACCESS_CLIENT_ID = "E2E_ACCESS_CLIENT_ID"
ACCESS_CLIENT_SECRET = "E2E_ACCESS_CLIENT_SECRET"  # noqa: S105 (a variable name)
LOGIN_EMAIL = "E2E_LOGIN_EMAIL"
LOGIN_PASSWORD = "E2E_LOGIN_PASSWORD"  # noqa: S105 (a variable name)

# The suite is only ever pointed at staging: production holds real data, and
# a running site can't be switched to another environment for one test.
REMOTE_ENVIRONMENT = "staging"


def remote_site(environ: Mapping[str, str]) -> str | None:
    """The running site's address, or None for Django's live server."""
    url = environ.get(SITE_URL, "").strip().rstrip("/")
    if not url:
        return None
    if not url.startswith("https://"):
        raise ValueError(f"{SITE_URL} must start with https://, not {url!r}")
    return url


def access_headers(environ: Mapping[str, str]) -> dict[str, str]:
    """Cloudflare Access service-token headers, or none if no token is set."""
    client_id = environ.get(ACCESS_CLIENT_ID, "").strip()
    secret = environ.get(ACCESS_CLIENT_SECRET, "").strip()
    if not client_id and not secret:
        return {}
    if not client_id or not secret:
        raise ValueError(
            f"Set both {ACCESS_CLIENT_ID} and {ACCESS_CLIENT_SECRET}, or neither"
        )
    return {"CF-Access-Client-Id": client_id, "CF-Access-Client-Secret": secret}


def login_account(environ: Mapping[str, str]) -> tuple[str, str] | None:
    """The practice account's email and password, or None if not set.

    The password is used exactly as given: spaces can be part of it.
    """
    email = environ.get(LOGIN_EMAIL, "").strip()
    password = environ.get(LOGIN_PASSWORD, "")
    if not email and not password.strip():
        return None
    if not email or not password:
        raise ValueError(f"Set both {LOGIN_EMAIL} and {LOGIN_PASSWORD}, or neither")
    return email, password
