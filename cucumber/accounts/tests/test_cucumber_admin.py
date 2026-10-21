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
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

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
from cucumber.core.audit import SYSTEM_USERNAME
from cucumber.core.tests.stock import make_staff, switch_off
from cucumber.core.tests.trail import audit_mark, audit_rows_since

pytestmark = pytest.mark.django_db


def staff_count() -> int:
    """Accounts other than System, which migrations add (U0.7 design §5.2)."""
    return User.objects.exclude(username=SYSTEM_USERNAME).count()


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


def test_the_trail_names_the_ssh_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """G4 review #3: System made the change; `via` says who ran the command."""
    monkeypatch.setenv("SSH_USER", "sawat")
    monkeypatch.setenv("SSH_CONNECTION", "203.0.113.5 52211 10.0.0.2 22")
    mark = audit_mark()

    run_command(Answers("jade@example.com", "Jade"))

    vias = {row.via for row in audit_rows_since(mark, "auth_user")}
    assert vias == {"cucumber_admin by sawat (ssh 203.0.113.5 52211 10.0.0.2 22)"}


# ----------------------------------------------------------------- rescue
def test_lets_a_locked_out_admin_back_in() -> None:
    jade = make_staff("jade", "admin", "forgotten-pw-77")
    switch_off(jade)
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


def test_lets_back_in_an_admin_whose_group_is_not_a_role() -> None:
    """An old group (a flag's `Owner`) reads as no role, never a crash (G4 M1)."""
    jade = make_staff("jade", "Owner")

    run_command(Answers("jade@example.com", promote="y"))

    groups = User.objects.get(pk=jade.pk).groups.values_list("name", flat=True)
    assert list(groups) == [ADMIN]
    assert can_log_in("jade@example.com")


def test_locks_the_admins_before_it_writes_the_account() -> None:
    """The Staff pages' lock order, so the two can't wait on each other (G4 L2)."""
    make_staff("jade", "admin", "forgotten-pw-77")

    with CaptureQueriesContext(connection) as queries:
        run_command(Answers("jade@example.com"))

    sql = [query["sql"] for query in queries.captured_queries]
    lock = next(i for i, text in enumerate(sql) if "FOR NO KEY UPDATE" in text)
    write = next(
        i for i, text in enumerate(sql) if text.startswith('UPDATE "auth_user"')
    )
    assert lock < write


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


def test_a_closed_keyboard_stops_cleanly_and_adds_nothing() -> None:
    """Input piped in, or Ctrl-D: a plain message, not a traceback (G4 M8)."""

    def no_more_input(prompt: str = "") -> str:
        raise EOFError

    with (
        mock.patch("builtins.input", no_more_input),
        pytest.raises(CommandError, match="Nothing was changed"),
    ):
        call_command("cucumber_admin", stdout=StringIO())

    assert staff_count() == 0


def roles_of(user: User) -> list[str]:
    return sorted(User.objects.get(pk=user.pk).groups.values_list("name", flat=True))


# ------------------------------------------------ U0.6 AC9: one role only
def test_the_first_admin_has_only_the_admin_role() -> None:
    run_command(Answers("jade@example.com"))

    assert roles_of(User.objects.get(username="jade@example.com")) == ["admin"]


@pytest.mark.parametrize("role", ["tech", "supervisor", "read_only"])
def test_promoting_replaces_the_role_the_account_had(role: str) -> None:
    gene = make_staff("gene", role, "genes-own-pw-55")

    run_command(Answers("gene@example.com", "Gene", promote="y"))

    assert roles_of(gene) == ["admin"]


def test_promoting_an_account_without_a_role_gives_it_admin() -> None:
    gene = make_staff("gene", None, "genes-own-pw-55")

    run_command(Answers("gene@example.com", "Gene", promote="y"))

    assert roles_of(gene) == ["admin"]


def test_promoting_logs_the_role_change_by_the_command(
    caplog: pytest.LogCaptureFixture,
) -> None:
    gene = make_staff("gene", "tech", "genes-own-pw-55")
    caplog.set_level(logging.INFO, logger="cucumber.accounts")

    run_command(Answers("gene@example.com", "Gene", promote="y"))

    assert f"role changed account={gene.pk} from=tech to=admin by=command" in (
        caplog.messages
    )


def test_rescuing_an_admin_logs_no_role_change(
    caplog: pytest.LogCaptureFixture,
) -> None:
    make_staff("jade", "admin", "forgotten-pw-77")
    caplog.set_level(logging.INFO, logger="cucumber.accounts")

    run_command(Answers("jade@example.com"))

    assert not any(m.startswith("role changed") for m in caplog.messages)


# -------------------------------------------- U0.6 AC17: name too long
def test_a_name_over_150_characters_is_refused_and_nothing_is_added() -> None:
    with pytest.raises(CommandError, match="150"):
        run_command(Answers("jade@example.com", "J" * 151))

    assert not User.objects.filter(username="jade@example.com").exists()


def test_a_closed_keyboard_at_the_password_stops_cleanly() -> None:
    def no_more_input(prompt: str = "") -> str:
        raise EOFError

    with (
        mock.patch("builtins.input", Answers("jade@example.com").input),
        mock.patch("getpass.getpass", no_more_input),
        pytest.raises(CommandError, match="Nothing was changed"),
    ):
        call_command("cucumber_admin", stdout=StringIO())

    assert staff_count() == 0
