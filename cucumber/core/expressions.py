"""Database expressions shared by the models."""

from typing import Any

from django.db.models import DateTimeField, Func


class TransactionNow(Func):
    """PostgreSQL `now()`: the time the transaction started.

    Django's `Now()` is `STATEMENT_TIMESTAMP()` on PostgreSQL. Cucumber's
    defaults use `now()` (U0.2 design §2) like the `recorded_at` trigger, so
    every row one save writes carries the same time.
    """

    template = "now()"

    def __init__(self, **extra: Any) -> None:
        super().__init__(output_field=DateTimeField(), **extra)
