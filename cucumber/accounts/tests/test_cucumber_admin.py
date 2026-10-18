"""AC29: `cucumber_admin`, the first Admin and the Owner's way back in (design §9).

The command asks with `input()` (email, name, "Make … an Admin? [y/N]") and
`getpass.getpass()` (the password, twice), both called through their
modules. The fakes answer by what the question says ("[y/N]" marks the
yes/no one), so the order of the questions is the command's choice. A
refused answer stops the command with CommandError; it doesn't ask again.
"""

import logging
from io import StringIO
from unittest import mock

import pytest
from django.contrib.auth.models import User
from django.core.management import CommandError, call_command
from django.test import Client

from cucumber.accounts.services import ADMIN, has_role
from cucumber.accounts.tests.helpers import (
    NEW_PASSWORD,
    add_failures,
    change_due,
    failures,
    log_in,
    mark_change_due,
    signed_in_as,
)
from cucumber.core.tests.stock import make_staff

pytestmark = pytest.mark.django_db


class Answers:
    """What the person at the terminal types."""

    def __init__(
        self,
        email: str,
        name: str = "Jade",
        passwords: tuple[str, str] = (NEW_PASSWORD, NEW_PASSWORD),
        promote: str = "n",
    ) -> None:
        self.email = email
        self.name = name
        self.passwords = iter(passwords)
        self.promote = promote
        self.asked_to_promote = False

    def input(self, prompt: str = "") -> str:
        question = prompt.lower()
        if "[y/n]" in question:
            self.asked_to_promote = True
            return self.promote
        if "email" in question:
            return self.email
        if "name" in question:
            return self.name
        raise AssertionError(f"unexpected question: {prompt!r}")

    def getpass(self, prompt: str = "") -> str:
        return next(self.passwords)


def run_command(answers: Answers) -> str:
    out = StringIO()
    with (
        mock.patch("builtins.input", answers.input),
        mock.patch("getpass.getpass", answers.getpass),
    ):
        call_command("cucumber_admin", stdout=out)
    return out.getvalue()


def can_log_in(email: str, password: str = NEW_PASSWORD) -> bool:
    client = Client()
    log_in(client, email, password)
    return signed_in_as(client) is not None


# ------------------------------------------------------------- first Admin
def test_adds_the_first_admin() -> None:
    run_command(Answers(" Jade@Example.com ", "Jade"))

    jade = User.objects.get(username="jade@example.com")
    assert jade.email == "jade@example.com"
    assert jade.first_name == "Jade"
    assert has_role(jade, ADMIN)
    assert not change_due(jade)
    assert can_log_in("jade@example.com")


# ----------------------------------------------------------------- rescue
def test_lets_a_locked_out_admin_back_in() -> None:
    jade = make_staff("jade", "admin", "forgotten-pw-77")
    User.objects.filter(pk=jade.pk).update(is_active=False)
    add_failures("jade@example.com", 5)
    mark_change_due(jade)
    answers = Answers("jade@example.com")

    run_command(answers)

    jade = User.objects.get(pk=jade.pk)
    assert jade.is_active
    assert failures("jade@example.com") == 0
    assert not change_due(jade)
    assert has_role(jade, ADMIN)
    assert not answers.asked_to_promote
    assert can_log_in("jade@example.com")


def test_writes_its_log_line(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="cucumber.accounts")

    run_command(Answers("jade@example.com"))

    jade = User.objects.get(username="jade@example.com")
    assert f"admin command account={jade.pk}" in caplog.messages
    assert NEW_PASSWORD not in caplog.text


def test_asks_before_making_someone_else_an_admin() -> None:
    gene = make_staff("gene", "tech", "genes-own-pw-55")
    answers = Answers("gene@example.com", "Gene", promote="n")

    run_command(answers)

    gene = User.objects.get(pk=gene.pk)
    assert answers.asked_to_promote
    assert not has_role(gene, ADMIN)
    assert gene.check_password("genes-own-pw-55")


def test_promotes_after_a_yes() -> None:
    gene = make_staff("gene", "tech", "genes-own-pw-55")

    run_command(Answers("gene@example.com", "Gene", promote="y"))

    assert has_role(User.objects.get(pk=gene.pk), ADMIN)
    assert can_log_in("gene@example.com")


# ------------------------------------------------------------ the rules
@pytest.mark.parametrize("weak", ["short1", "password123", "4815162342"])
def test_a_weak_password_is_refused_and_nothing_is_added(weak: str) -> None:
    with pytest.raises(CommandError):
        run_command(Answers("jade@example.com", passwords=(weak, weak)))

    assert not User.objects.filter(username="jade@example.com").exists()


def test_two_different_passwords_are_refused() -> None:
    with pytest.raises(CommandError):
        run_command(
            Answers("jade@example.com", passwords=(NEW_PASSWORD, "fern-lantern-88"))
        )

    assert not User.objects.filter(username="jade@example.com").exists()


@pytest.mark.parametrize("email", ["", "jade", "jade@"])
def test_a_broken_email_is_refused(email: str) -> None:
    count = User.objects.count()

    with pytest.raises(CommandError):
        run_command(Answers(email))

    assert User.objects.count() == count
