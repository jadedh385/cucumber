"""`cucumber_anonymise`: remove a former staff member's details (AC12–AC14).

Asks for the account's email, says what will happen, and goes on only when
`ANONYMISE` is typed. The name becomes `Former staff #<id>`; everything the
person saved stays under the same id (U0.7 design §7.2). Run on the server.
"""

from typing import Any

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from cucumber.accounts.management.commands.cucumber_admin import ask
from cucumber.accounts.services import anonymise, email_key
from cucumber.core.refusals import Refused

CONFIRM_WORD = "ANONYMISE"


class Command(BaseCommand):
    help = "Remove a former staff member's personal details (PDPA request)."

    def handle(self, *args: Any, **options: Any) -> None:
        account = find_account(ask("Email: "))
        shown = account.first_name or account.email
        former = f"Former staff #{account.pk}"
        self.stdout.write(
            f'{shown} (#{account.pk}) will become "{former}". Their name and'
            " email are removed for good; everything they saved stays under"
            f" #{account.pk}. This can't be undone."
        )
        if ask(f"Type {CONFIRM_WORD} to go on: ").strip() != CONFIRM_WORD:
            self.stdout.write("Nothing was changed.")
            return
        try:
            anonymise(account)
        except Refused as refusal:
            raise CommandError(refusal.message.format(name=shown)) from None
        self.stdout.write(f"#{account.pk} is now {former}.")


def find_account(typed: str) -> User:
    account = User.objects.filter(username=email_key(typed)).first()
    if account is None:
        raise CommandError("No account with that email. Nothing was changed.")
    return account
