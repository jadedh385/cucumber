"""`cucumber_anonymise`: remove a former staff member's details (AC12–AC14).

Asks for the account's email, says what will happen, and goes on only when
`ANONYMISE` is typed. The name becomes `Former staff #<id>`; everything the
person saved stays under the same id (U0.7 design §7.2). Run on the server.
"""

from typing import Any

from django.core.management.base import BaseCommand

CONFIRM_WORD = "ANONYMISE"


class Command(BaseCommand):
    help = "Remove a former staff member's personal details (PDPA request)."

    def handle(self, *args: Any, **options: Any) -> None:
        raise NotImplementedError("U0.7 G3")
