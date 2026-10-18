"""`cucumber_admin`: the first Admin, or the Owner's way back in (AC29, design §9).

Asks for an email, a name and a password (twice, hidden). Adds an Admin
account, or resets an existing one: new password, active, unlocked, no
change due. Asks before making someone an Admin who isn't one already.
"""

from typing import Any

from django.core.management.base import BaseCommand

from cucumber.accounts.services import NOT_BUILT


class Command(BaseCommand):
    help = "Add the first Admin, or let the Owner back in (run on the server)."

    def handle(self, *args: Any, **options: Any) -> None:
        raise NotImplementedError(NOT_BUILT)
