"""`manage.py cucumber_audit`: read the audit trail (AC9, U0.7 design §7.1).

    cucumber_audit [--person <id or email>] [--table plants] [--row 42]
                   [--since 2026-10-01] [--until 2026-10-20] [--limit 50]

Newest first, in Bangkok time, at most `--limit` rows, with the total.
People are shown by id, never by name or email (AC8). Read-only.
"""

import json
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db.models import QuerySet
from waffle.models import Flag

from cucumber.accounts.services import email_key
from cucumber.core.audit import system_account
from cucumber.core.models import AuditLog

DEFAULT_LIMIT = 50
BANGKOK = ZoneInfo("Asia/Bangkok")
FLAG_TABLES = {"waffle_flag", "waffle_flag_groups"}


class Command(BaseCommand):
    help = "List audit rows by person, table, row and date (newest first)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--person", help="an account id or email")
        parser.add_argument("--table", help="a table name, e.g. plants")
        parser.add_argument("--row", help="the row's key, e.g. 42")
        parser.add_argument("--since", help="from this Bangkok date, YYYY-MM-DD")
        parser.add_argument("--until", help="to this Bangkok date, YYYY-MM-DD")
        parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)

    def handle(self, *args: Any, **options: Any) -> None:
        rows = filtered(AuditLog.objects.all(), options).order_by("-at", "-id")
        total = rows.count()
        shown = list(rows[: options["limit"]])
        names = Names(system_account().pk)
        for row in shown:
            for line in describe(row, names):
                self.stdout.write(line)
        self.stdout.write(f"{len(shown)} of {total} rows")


def filtered(rows: QuerySet[AuditLog], options: dict[str, Any]) -> QuerySet[AuditLog]:
    if options["person"]:
        rows = rows.filter(actor_id=person_id(options["person"]))
    if options["table"]:
        rows = rows.filter(table_name=options["table"])
    if options["row"]:
        rows = rows.filter(row_pk=options["row"])
    if options["since"]:
        rows = rows.filter(at__gte=start_of(options["since"]))
    if options["until"]:
        rows = rows.filter(at__lt=start_of(options["until"]) + timedelta(days=1))
    return rows


def person_id(typed: str) -> int:
    """An account id, given its id or its email; anonymised ones by id only."""
    text = typed.strip()
    found = (
        User.objects.filter(pk=int(text))
        if text.isdigit()
        else User.objects.filter(username=email_key(text))
    )
    pk = found.values_list("pk", flat=True).first()
    if pk is None:
        raise CommandError(f"No account with the id or email {text}.")
    return pk


def start_of(day: str) -> datetime:
    """Midnight in Bangkok at the start of `day` (YYYY-MM-DD)."""
    try:
        date = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError:
        raise CommandError(f"{day} isn't a date; write it as YYYY-MM-DD.") from None
    return datetime.combine(date, time(0), tzinfo=BANGKOK)


class Names:
    """Ids shown as names where that is no personal data: flags and roles."""

    def __init__(self, system_id: int) -> None:
        self.system_id = system_id
        self.groups: dict[int, str] = dict(Group.objects.values_list("pk", "name"))
        self.flags: dict[int, str] = dict(Flag.objects.values_list("pk", "name"))

    def actor(self, row: AuditLog) -> str:
        if row.actor_id is None:
            return "nobody"
        return "System" if row.actor_id == self.system_id else f"#{row.actor_id}"

    def row(self, row: AuditLog) -> str:
        if row.table_name in FLAG_TABLES and row.row_pk.isdigit():
            return self.flags.get(int(row.row_pk), row.row_pk)
        return row.row_pk

    def value(self, column: str, value: object) -> str:
        if column == "group_id" and isinstance(value, int):
            return self.groups.get(value, str(value))
        return json.dumps(value, ensure_ascii=False)


def describe(row: AuditLog, names: Names) -> list[str]:
    """The row's line, and its reason line when it has one."""
    when = row.at.astimezone(BANGKOK).strftime("%Y-%m-%d %H:%M")
    who = f"{names.actor(row)} ({row.via})"
    what = f"{row.table_name} {names.row(row)}"
    lines = [f"{when}  {who}  {what}  {row.action}  {changes(row, names)}".rstrip()]
    if row.reason_id:
        note = f' "{row.note}"' if row.note else ""
        lines.append(f"{' ' * len(when)}  reason: {row.reason_id}{note}")
    return lines


def changes(row: AuditLog, names: Names) -> str:
    """`column: before → after, …`; a column only added or removed shows one value."""
    before = row.before or {}
    after = row.after or {}
    parts = []
    for column in [*before, *(c for c in after if c not in before)]:
        if column in before and column in after:
            old, new = (
                names.value(column, before[column]),
                names.value(column, after[column]),
            )
            parts.append(f"{column}: {old} → {new}")
        else:
            only = after[column] if column in after else before[column]
            parts.append(f"{column}: {names.value(column, only)}")
    return ", ".join(parts)
