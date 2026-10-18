"""Helpers for the U0.5 tests: logging in, the lock table, sessions, pages.

The lock and change-due tables are read with plain SQL by their design
names (§3.1, §3.2), as the U0.2a schema tests do, so the tests don't depend
on how the models are written. Time is moved by ageing rows in the
database, so the tests don't depend on whose clock the code reads.
"""

import re
from datetime import timedelta
from http.cookies import SimpleCookie
from typing import Protocol
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.test import Client

from cucumber.core.tests.rows import as_int, fetch_one, run

LOGIN = "/accounts/login/"
LOGOUT = "/accounts/logout/"
PASSWORD_PAGE = "/accounts/password/"  # noqa: S105 (an address)
HOME = "/"
STAFF = "/staff/"

PASSWORD = "plum-orchid-42"  # noqa: S105 (a test account's password)
NEW_PASSWORD = "fern-lantern-87"  # noqa: S105
ADDRESS = "203.0.113.7"  # documentation range (RFC 5737)
OTHER_ADDRESS = "198.51.100.9"

# Design §2.2.
WRONG = "Email or password is wrong."
LOCKED = "Too many tries. Wait 15 minutes or ask the Owner."

# Design §7.3: 12 of these, in three groups of four joined by dashes.
TEMPORARY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
TEMPORARY_PASSWORD = re.compile(
    rf"\b[{TEMPORARY_ALPHABET}]{{4}}-[{TEMPORARY_ALPHABET}]{{4}}"
    rf"-[{TEMPORARY_ALPHABET}]{{4}}\b"
)
LOOK_ALIKES = set("0o1li")


class Response(Protocol):
    """What the tests read from an answer, the test client's included."""

    @property
    def status_code(self) -> int: ...

    @property
    def content(self) -> bytes: ...

    @property
    def cookies(self) -> SimpleCookie: ...

    def get(self, header: str) -> str | None: ...

    def __getitem__(self, header: str) -> str: ...


# ------------------------------------------------------------------- logging in


def log_in(
    client: Client, email: str, password: str = PASSWORD, address: str = ADDRESS
) -> Response:
    """POST the login form as a phone at `address` would."""
    response: Response = client.post(
        LOGIN, {"username": email, "password": password}, REMOTE_ADDR=address
    )
    return response


def signed_in(user: User) -> Client:
    """A client that logged in through the login page, as a person would."""
    client = Client()
    response = log_in(client, user.username)
    assert response.status_code == 302, f"{user.username} could not log in"
    return client


def session_ended(client: Client) -> bool:
    """True when this client's next page goes to login.

    Asked through a request: Django ends a session whose password changed only
    when that session next opens a page, so the stored row alone can't tell.
    """
    response = client.get(HOME)
    return response.status_code == 302 and redirect_target(response)[0] == LOGIN


def shows_signed_in(html: str, who: str) -> bool:
    """The page says "Signed in as <who>", markup around the name allowed."""
    pattern = rf"Signed in as\s*(?:<[^>]+>\s*)*{re.escape(who)}\s*<"
    return re.search(pattern, html) is not None


def signed_in_as(client: Client) -> int | None:
    """The account id this client's session belongs to, if any."""
    user_id = client.session.get("_auth_user_id")
    return None if user_id is None else int(user_id)


def text(response: Response) -> str:
    return response.content.decode()


def redirect_target(response: Response) -> tuple[str, dict[str, list[str]]]:
    """The path and query of a redirect (or an HX-Redirect)."""
    location = response.get("HX-Redirect") or response["Location"]
    parts = urlsplit(location)
    return parts.path, parse_qs(parts.query)


def without_values(html: str) -> str:
    """The page with every `value="…"` emptied (CSRF token, echoed email)."""
    return re.sub(r'value="[^"]*"', 'value=""', html)


def temporary_password_in(response: Response) -> str:
    found = TEMPORARY_PASSWORD.findall(text(response))
    assert len(found) == 1, f"expected one temporary password, found {found}"
    password: str = found[0]
    return password


def htmx_headers(page: str = "http://testserver/staff/") -> dict[str, str]:
    """What htmx sends with a background request from `page`."""
    return {"HX-Request": "true", "HX-Current-URL": page}


# ----------------------------------------------------------------- lock table


def failures(email: str) -> int:
    row = fetch_one(
        "SELECT count(*) FROM accounts_login_failure WHERE email_key = %s", [email]
    )
    return as_int(row[0])


def failures_from(address: str) -> int:
    row = fetch_one(
        "SELECT count(*) FROM accounts_login_failure WHERE address = %s::inet",
        [address],
    )
    return as_int(row[0])


def age_failures(by: timedelta) -> None:
    """Move every counted failure `by` into the past."""
    run("UPDATE accounts_login_failure SET at = at - %s", [by])


def add_failures(email: str, count: int, address: str | None = ADDRESS) -> None:
    """Count wrong tries straight into the table, as `login_failed` would."""
    for _ in range(count):
        run(
            "INSERT INTO accounts_login_failure (email_key, address, at)"
            " VALUES (%s, %s::inet, now())",
            [email, address],
        )


# ------------------------------------------------------------ change due


def change_due(user: User) -> bool:
    row = fetch_one(
        "SELECT count(*) FROM accounts_password_change_due WHERE user_id = %s",
        [user.pk],
    )
    return row[0] == 1


def mark_change_due(user: User) -> None:
    run(
        "INSERT INTO accounts_password_change_due (user_id, since) VALUES (%s, now())",
        [user.pk],
    )


# ------------------------------------------------------------------ sessions


def end_idle_sessions_now() -> None:
    """As if 7 days passed with no page opened: every session has expired."""
    run("UPDATE django_session SET expire_date = now() - interval '1 second'")


def set_login_age(client: Client, age: timedelta) -> None:
    """Pretend this client logged in `age` ago (the `login_at` stamp, §5)."""
    session = client.session
    login_at = session["login_at"]
    assert isinstance(login_at, int), f"login_at should be whole seconds: {login_at!r}"
    session["login_at"] = login_at - int(age.total_seconds())
    session.save()


def all_session_data() -> str:
    """Every session's stored data, raw and decoded, as one text."""
    rows = Session.objects.all()
    return "\n".join(f"{row.session_data}\n{row.get_decoded()}" for row in rows)
