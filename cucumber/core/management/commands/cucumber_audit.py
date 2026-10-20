"""`manage.py cucumber_audit`: read the audit trail (AC9, U0.7 design §7.1).

    cucumber_audit [--person <id or email>] [--table plants] [--row 42]
                   [--since 2026-10-01] [--until 2026-10-20] [--limit 50]

Newest first, in Bangkok time, at most `--limit` rows, with the total.
People are shown by id, never by name or email (AC8). Read-only.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

DEFAULT_LIMIT = 50


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
        raise NotImplementedError("U0.7 G3")
