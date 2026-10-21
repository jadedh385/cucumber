"""The 10× timing check for logging in (U0.5 G5).

Loads 10 times today's accounts (about 10 staff, each on up to 3 phones or
computers) into the throwaway database `cucumber_timing`, with a generous
pile of rows that grow with use: sessions that have ended but aren't cleared
yet, and wrong-password tries from the last day and older. Then times what
staff and the Admin do, through Django's test client, so every middleware
and the real password hasher run. Run it with `uat/timing_10x.sh`.

Logging in is slow on purpose: checking a password takes a fixed, deliberate
amount of work (Django's hasher), so guessing passwords is slow too.
"""

import os
import time
from dataclasses import dataclass
from datetime import timedelta

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cucumber.settings")
django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import (  # noqa: E402
    BACKEND_SESSION_KEY,
    HASH_SESSION_KEY,
    SESSION_KEY,
)
from django.contrib.auth.hashers import make_password  # noqa: E402
from django.contrib.auth.models import User  # noqa: E402
from django.contrib.sessions.backends.db import SessionStore  # noqa: E402
from django.contrib.sessions.models import Session  # noqa: E402
from django.db import connection  # noqa: E402
from django.test import Client  # noqa: E402
from django.urls import reverse  # noqa: E402
from django.utils import timezone  # noqa: E402
from django.utils.crypto import get_random_string  # noqa: E402

from cucumber.accounts.middleware import LOGIN_AT  # noqa: E402
from cucumber.accounts.permissions import Role  # noqa: E402
from cucumber.accounts.services import replace_role  # noqa: E402
from cucumber.core.audit import SYSTEM, audited  # noqa: E402
from scripts.timing_10x import (  # noqa: E402
    LOADED_BY,
    RUNS,
    Summary,
    as_table,
    check_database,
    run_sql,
    timed,
)

PASSWORD = "timing-login-pw-7f3k"  # noqa: S105 (made-up, throwaway database only)
SESSION_KEY_LENGTH = 32
FOUND = 200
REDIRECT = 302

LABELS = (
    "First login after a quiet week (clears ended sessions)",
    "Log in, right password",
    "Log in, wrong password",
    "Open a page, signed in",
    "Staff page, all accounts",
    "Give someone a new password (ends their sessions)",
)


@dataclass(frozen=True)
class LoginScale:
    """How much to load. The defaults are 10× today, with room to spare."""

    accounts: int = 100
    devices: int = 3  # live sessions per account
    ended_sessions: int = 3_000  # a month of daily logins, not yet cleared
    recent_failures: int = 5_000  # wrong passwords in the last day
    old_failures: int = 5_000  # older than a day, cleared at the next login

    @property
    def live_sessions(self) -> int:
        return self.accounts * self.devices


# ---------------------------------------------------------------- plain parts


def email(number: int) -> str:
    return f"timing-login-{number}@example.com"


def expect(action: str, got: int, wanted: int) -> None:
    """Stop the run if a page answered something other than expected."""
    if got != wanted:
        raise SystemExit(f"{action}: expected {wanted}, got {got}")


# ------------------------------------------------------------------- the load


def load_accounts(scale: LoginScale) -> list[User]:
    """The accounts, all with the same password; the first is an Admin."""
    hashed = make_password(PASSWORD)  # once: hashing each would take minutes
    accounts = User.objects.bulk_create(
        User(
            username=email(n), email=email(n), first_name=f"Timing {n}", password=hashed
        )
        for n in range(1, scale.accounts + 1)
    )
    replace_role(accounts[0], Role.ADMIN)
    return accounts


def signed_in_as(account: User) -> dict[str, object]:
    """What Django keeps in a session for a signed-in account."""
    return {
        SESSION_KEY: str(account.pk),
        BACKEND_SESSION_KEY: settings.AUTHENTICATION_BACKENDS[0],
        HASH_SESSION_KEY: account.get_session_auth_hash(),
        LOGIN_AT: int(time.time()),
    }


def load_sessions(scale: LoginScale, accounts: list[User]) -> None:
    store = SessionStore()
    now = timezone.now()
    live = (
        Session(
            session_key=get_random_string(SESSION_KEY_LENGTH),
            session_data=store.encode(signed_in_as(account)),
            expire_date=now + timedelta(days=7),
        )
        for account in accounts
        for _ in range(scale.devices)
    )
    ended = (
        Session(
            session_key=get_random_string(SESSION_KEY_LENGTH),
            session_data=store.encode({}),
            expire_date=now - timedelta(days=1 + n % 20),
        )
        for n in range(scale.ended_sessions)
    )
    Session.objects.bulk_create([*live, *ended])


def load_failures(scale: LoginScale) -> None:
    """Wrong passwords for emails no account has, from many addresses."""
    run_sql(
        """INSERT INTO accounts_login_failure (email_key, address, at)
           SELECT 'nobody-' || n || '@example.com',
                  ('10.1.' || (n / 200) %% 256 || '.' || n %% 200)::inet,
                  now() - (n %% 1400) * interval '1 minute'
                        - CASE WHEN n <= %(recent)s THEN interval '0'
                               ELSE interval '2 days' END
           FROM generate_series(1, %(total)s) AS n""",
        {
            "recent": scale.recent_failures,
            "total": scale.recent_failures + scale.old_failures,
        },
    )


def load(scale: LoginScale) -> list[User]:
    with audited(SYSTEM, via=LOADED_BY):  # accounts are audited (U0.7 AC6)
        accounts = load_accounts(scale)
    load_sessions(scale, accounts)
    load_failures(scale)
    run_sql("ANALYZE")
    return accounts


# ---------------------------------------------------------------- the timings


def browser() -> Client:
    return Client(HTTP_HOST=settings.ALLOWED_HOSTS[0])


def log_in(account: User) -> Client:
    client = browser()
    answer = client.post(
        reverse("login"), {"username": account.username, "password": PASSWORD}
    )
    expect("Log in", answer.status_code, REDIRECT)
    return client


def wrong_password(number: int) -> None:
    answer = browser().post(
        reverse("login"),
        {"username": f"wrong-{number}@example.com", "password": "nope"},
    )
    expect("Wrong password", answer.status_code, FOUND)


def opened(client: Client, url: str) -> None:
    expect(f"Open {url}", client.get(url).status_code, FOUND)


def measure(scale: LoginScale, runs: int) -> list[tuple[str, Summary]]:
    accounts = list(
        User.objects.filter(username__startswith="timing-login-").order_by("pk")
    )
    if len(accounts) != scale.accounts:
        raise SystemExit(f"Load {scale.accounts} accounts first, found {len(accounts)}")
    admin, staff = accounts[0], accounts[1:]

    def someone(number: int) -> User:
        return staff[number % len(staff)]

    summaries = [timed(lambda n: log_in(someone(n)), 1)]
    summaries.append(timed(lambda n: log_in(someone(n)), runs))
    summaries.append(timed(wrong_password, runs))
    admin_client = log_in(admin)

    def give_new_password(number: int) -> None:
        url = reverse("staff_new_password", args=[someone(number).pk])
        expect("New password", admin_client.post(url).status_code, FOUND)

    summaries.append(timed(lambda n: opened(admin_client, reverse("home")), runs))
    summaries.append(timed(lambda n: opened(admin_client, reverse("staff")), runs))
    summaries.append(timed(give_new_password, runs))
    return list(zip(LABELS, summaries, strict=True))


def main() -> None:
    check_database(connection.settings_dict["NAME"])
    load(LoginScale())
    print(as_table(measure(LoginScale(), RUNS)))


if __name__ == "__main__":
    main()
