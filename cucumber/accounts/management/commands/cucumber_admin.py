"""`cucumber_admin`: the first Admin, or the Owner's way back in (AC29, design §9).

Asks for an email, a name and a password (twice, hidden). Adds an Admin
account, or resets an existing one: new password, active, unlocked, no
change due. Asks before making someone an Admin who isn't one already.

A refused answer, or no answer at all (Ctrl-D, or input piped in that
runs out), stops the command; run it again to retry.
"""

import getpass
import logging
from typing import Any

from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from cucumber.accounts.models import LoginFailure, PasswordChangeDue
from cucumber.accounts.services import ADMIN, checked_email, has_role
from cucumber.core.refusals import Refused

logger = logging.getLogger(__name__)

NO_ANSWER = "No answer was typed. Nothing was changed."


def ask(question: str, hidden: bool = False) -> str:
    """One answer from the terminal; a closed keyboard stops cleanly (G4 M8)."""
    try:
        return getpass.getpass(question) if hidden else input(question)
    except EOFError:
        raise CommandError(NO_ANSWER) from None


def ask_email() -> str:
    try:
        return checked_email(ask("Email: "))
    except Refused as refusal:
        raise CommandError(refusal.message) from None


def ask_password(account: User) -> str:
    """The new password, typed twice and checked by Django's four rules."""
    first = ask("New password: ", hidden=True)
    second = ask("New password again: ", hidden=True)
    if first != second:
        raise CommandError("The two passwords are different. Nothing was changed.")
    try:
        validate_password(first, user=account)
    except ValidationError as error:
        raise CommandError(" ".join(error.messages)) from None
    return first


class Command(BaseCommand):
    help = "Add the first Admin, or let the Owner back in (run on the server)."

    def handle(self, *args: Any, **options: Any) -> None:
        email = ask_email()
        existing = User.objects.filter(username=email).first()
        if existing is None:
            name = ask("Name: ").strip()
            account = User(username=email, email=email, first_name=name)
        else:
            account = existing
            if not has_role(account, ADMIN):
                shown = account.first_name or email
                answer = ask(f"Make {shown} an Admin? [y/N] ")
                if answer.strip().lower() != "y":
                    self.stdout.write("Nothing was changed.")
                    return
        password = ask_password(account)
        self.save(account, password)
        logger.info("admin command account=%s", account.pk)
        self.stdout.write(f"{email} is an Admin and can log in now.")

    def save(self, account: User, password: str) -> None:
        """Password, active, Admin, unlocked and no change due, all together."""
        with transaction.atomic():
            account.set_password(password)
            account.is_active = True
            account.save()
            admin, _ = Group.objects.get_or_create(name=ADMIN)
            account.groups.add(admin)
            LoginFailure.objects.filter(email_key=account.username).delete()
            PasswordChangeDue.objects.filter(user_id=account.pk).delete()
