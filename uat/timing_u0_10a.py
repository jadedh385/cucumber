"""U0.10a G5 timing: the slowest single statement at 10× data, and the pages every
person opens (design §8.1, §6.2).

The server cancels any one statement after 10 s (`statement_timeout`). This loads
the usual 10× data (`scripts.timing_10x`) and 100 accounts (`scripts.timing_login`)
into the throwaway `cucumber_timing` database, runs both scripts' timings, and
notes how long each statement took and what it was. Then it opens Home and the
Staff list as each role and counts the queries. Run it from the repo root:

    PYTHONPATH=. .venv/bin/python uat/timing_u0_10a.py

with `DB_NAME=cucumber_timing` in the environment and the database migrated (the
same set-up as `uat/timing_10x.sh`, which this does not replace).
"""

import os
import sys
import time
from collections.abc import Callable
from typing import Any

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cucumber.settings")

import django  # noqa: E402

django.setup()

from django.db import connection  # noqa: E402
from django.urls import reverse  # noqa: E402

from cucumber.accounts.permissions import Role  # noqa: E402
from cucumber.accounts.services import replace_role  # noqa: E402
from cucumber.core.audit import SYSTEM, audited  # noqa: E402
from scripts import timing_10x as base  # noqa: E402
from scripts import timing_login as login  # noqa: E402

STATEMENT_LIMIT_SECONDS = 10
SLOWEST_SHOWN = 5
PAGE_RUNS = 30
SQL_SHOWN = 110
Execute = Callable[..., Any]


class Slowest:
    """The statements that took longest, seen from Django's connection."""

    def __init__(self) -> None:
        self.seen: list[tuple[float, str]] = []

    def __call__(
        self, execute: Execute, sql: str, params: Any, many: bool, context: Any
    ) -> Any:
        started = time.perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            self.seen.append((time.perf_counter() - started, " ".join(sql.split())))

    def table(self) -> str:
        top = sorted(self.seen, reverse=True)[:SLOWEST_SHOWN]
        rows = [f"| {s * 1000:,.1f} ms | `{sql[:SQL_SHOWN]}` |" for s, sql in top]
        return "\n".join(["| Took | Statement |", "|--:|---|", *rows])


def page_row(slowest: Slowest, client: Any, name: str, url: str) -> str:
    client.get(url)  # warm
    before = len(slowest.seen)
    client.get(url)
    queries = slowest.seen[before:]
    summary = base.timed(lambda n: login.opened(client, url), PAGE_RUNS)
    return (
        f"| {name} | {len(queries)} | {summary.median:.1f} ms | {summary.p95:.1f} ms |"
    )


def page_table(slowest: Slowest, accounts: list[Any]) -> str:
    rows = ["| Page, as | Queries | Median | p95 |", "|---|--:|--:|--:|"]
    roles = (Role.ADMIN, Role.SUPERVISOR, Role.TECH, Role.READ_ONLY)
    for account, role in zip(accounts, roles, strict=False):
        if role is not Role.ADMIN:
            with audited(SYSTEM, via=base.LOADED_BY):
                replace_role(account, role)
        client = login.log_in(account)
        rows.append(page_row(slowest, client, f"Home, {role.value}", reverse("home")))
        if role is Role.ADMIN:
            rows.append(
                page_row(slowest, client, "Staff list, admin", reverse("staff"))
            )
    return "\n".join(rows)


def main() -> None:
    base.check_database(connection.settings_dict["NAME"])
    scale, login_scale = base.Scale(), login.LoginScale()
    # The loader's bulk inserts, not the app, run without the limit; every
    # connection after this one (each test-client request opens its own) has it.
    with connection.cursor() as cursor:
        cursor.execute("SET statement_timeout = 0")
        base.load(scale)
        accounts = login.load(login_scale)
        cursor.execute(f"SET statement_timeout = '{STATEMENT_LIMIT_SECONDS}s'")
    slowest = Slowest()
    with connection.execute_wrapper(slowest), base.connect_as_app() as app:
        base.measure(scale, base.RUNS, app)
        pages = page_table(
            slowest, accounts
        )  # before the login timings change passwords
        login.measure(login_scale, base.RUNS)
    sys.stdout.write(
        f"## Slowest statements (the limit is {STATEMENT_LIMIT_SECONDS} s)\n\n"
        f"{slowest.table()}\n\n{len(slowest.seen):,} statements seen.\n\n"
        f"## Pages\n\n{pages}\n"
    )


if __name__ == "__main__":
    main()
