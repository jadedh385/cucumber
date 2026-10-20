"""AC12–AC14: `cucumber_anonymise`, and the reserved System account (design §7.2).

The command asks with `input()`: the email, then the typed confirmation. The
fake answers by what the question says, like test_cucumber_admin.py's.
"""

import json
import logging
from collections.abc import Callable
from io import StringIO
from unittest import mock

import pytest
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core.management import CommandError, call_command
from django.test import Client

from cucumber.accounts.permissions import Role
from cucumber.accounts.services import (
    add_account,
    anonymise,
    deactivate,
    give_new_password,
    reactivate,
    set_role,
)
from cucumber.accounts.tests.helpers import (
    STAFF,
    add_failures,
    change_due,
    failures,
    log_in,
    mark_change_due,
    session_ended,
    signed_in_as,
    text,
)
from cucumber.accounts.tests.test_cucumber_admin import Answers, run_command
from cucumber.core.audit import SYSTEM_USERNAME, Reason, system_account
from cucumber.core.tests.rows import (
    fetch_one,
    insert,
    make_batch,
    make_event,
    make_plant,
    refused_by,
    run,
)
from cucumber.core.tests.stock import make_staff, refused
from cucumber.core.tests.trail import (
    LEFT_COMPANY,
    PDPA_CODE,
    as_system,
    audit_mark,
    named_in_sql,
    only_row,
    system_id,
)
from cucumber.events.models import Event

pytestmark = pytest.mark.django_db

REMOVED = "details were removed (PDPA)"


class Typed:
    """What the Owner types: the email, then the confirmation word."""

    def __init__(self, email: str, confirm: str = "ANONYMISE") -> None:
        self.email = email
        self.confirm = confirm
        self.asked: list[str] = []

    def input(self, prompt: str = "") -> str:
        self.asked.append(prompt)
        if "email" in prompt.lower():
            return self.email
        if "ANONYMISE" in prompt:
            return self.confirm
        raise AssertionError(f"unexpected question: {prompt!r}")


def anonymise_command(typed: Typed) -> str:
    out = StringIO()
    with mock.patch("builtins.input", typed.input):
        call_command("cucumber_anonymise", stdout=out)
    return out.getvalue()


def former(account: User) -> str:
    return f"former-staff-{account.pk}@cucumber.invalid"


def fresh(account: User) -> User:
    return User.objects.get(pk=account.pk)


# ------------------------------------------------------------------- AC12
def test_the_personal_details_are_replaced(owner: User, gene: User) -> None:
    anonymise_command(Typed("gene@example.com"))

    after = fresh(gene)
    assert after.first_name == f"Former staff #{gene.pk}"
    assert after.last_name == ""
    assert after.username == after.email == former(gene)
    assert after.has_usable_password() is False
    assert after.is_active is False


def test_the_command_says_what_will_happen_then_what_happened(
    owner: User, gene: User
) -> None:
    typed = Typed("gene@example.com")

    output = anonymise_command(typed)

    assert f'gene (#{gene.pk}) will become "Former staff #{gene.pk}"' in output
    assert "This can't be undone." in output
    assert f"#{gene.pk} is now Former staff #{gene.pk}." in output
    assert any("Type ANONYMISE to go on" in question for question in typed.asked)


def test_what_they_did_stays_under_the_same_id(owner: User, gene: User) -> None:
    with as_system():
        batch = make_batch(make_plant(owner.pk), owner.pk)
    event = make_event(batch, gene.pk, "count", counted_qty=0)
    insert(
        "audit_log",
        {
            "actor_id": gene.pk,
            "table_name": "auth_user",
            "row_pk": str(gene.pk),
            "action": "update",
            "after": json.dumps({"password": "changed"}),
            "via": "app",
        },
    )

    anonymise_command(Typed("gene@example.com"))

    saved = Event.objects.get(pk=event)
    assert (saved.recorded_by_id, saved.staff_id) == (gene.pk, gene.pk)
    by_gene = fetch_one("SELECT count(*) FROM audit_log WHERE actor_id = %s", [gene.pk])
    assert by_gene == (1,)


def test_sessions_lock_counts_and_change_due_go_but_the_role_stays(
    owner: User, gene: User, gene_client: Client
) -> None:
    add_failures("gene@example.com", 2)
    mark_change_due(gene)

    anonymise_command(Typed("gene@example.com"))

    assert session_ended(gene_client)
    assert failures("gene@example.com") == 0
    assert not change_due(gene)
    assert list(fresh(gene).groups.values_list("name", flat=True)) == ["tech"]


def test_nothing_else_changes(owner: User, gene: User, pim: User) -> None:
    before = {k: v for k, v in fresh(pim).__dict__.items() if k != "_state"}

    anonymise_command(Typed("gene@example.com"))

    after = {k: v for k, v in fresh(pim).__dict__.items() if k != "_state"}
    assert after == before


def test_no_session_is_left_for_an_anonymised_account(owner: User, gene: User) -> None:
    Client().force_login(gene)

    anonymise_command(Typed("gene@example.com"))

    owners = [s.get_decoded().get("_auth_user_id") for s in Session.objects.all()]
    assert str(gene.pk) not in owners


# ------------------------------------------------------------------- AC13
def test_the_anonymising_is_an_audit_row_without_personal_data(
    owner: User, gene: User
) -> None:
    mark = audit_mark()

    anonymise_command(Typed("gene@example.com"))

    row = only_row(mark, "auth_user")
    assert (row.actor_id, row.via, row.row_pk) == (
        system_id(),
        "cucumber_anonymise",
        str(gene.pk),
    )
    assert row.reason_code == PDPA_CODE
    assert row.after == {
        "first_name": "changed",
        "username": "changed",
        "email": "changed",
        "password": "changed",
        "is_active": False,
    }
    stored = json.dumps([row.before, row.after, row.note])
    assert "gene" not in stored.lower()


def test_the_log_line_names_the_id_only(
    owner: User, gene: User, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="cucumber.accounts")

    anonymise_command(Typed("gene@example.com"))

    assert f"account anonymised account={gene.pk}" in caplog.messages
    assert "gene@example.com" not in "\n".join(caplog.messages)


def test_an_anonymised_account_cant_log_in(owner: User, gene: User) -> None:
    anonymise_command(Typed("gene@example.com"))

    client = Client()
    log_in(client, former(gene))
    assert signed_in_as(client) is None


def test_an_anonymised_account_cant_be_reactivated(owner: User, gene: User) -> None:
    anonymise_command(Typed("gene@example.com"))

    with refused("account_anonymised"):
        reactivate(owner, fresh(gene))

    assert fresh(gene).is_active is False


def test_not_even_by_raw_sql(owner: User, gene: User) -> None:
    anonymise_command(Typed("gene@example.com"))

    with named_in_sql(owner.pk), refused_by("auth_user_anonymised_stays_off"):
        run("UPDATE auth_user SET is_active = true WHERE id = %s", [gene.pk])


def test_anonymising_twice_is_refused(owner: User, gene: User) -> None:
    anonymise_command(Typed("gene@example.com"))
    mark = audit_mark()

    with pytest.raises(CommandError, match=REMOVED):
        anonymise_command(Typed(former(gene)))

    assert audit_mark() == mark


def test_cucumber_admin_refuses_an_anonymised_account_by_name(
    owner: User, gene: User
) -> None:
    """Review L4: its message, not a raw constraint error."""
    anonymise_command(Typed("gene@example.com"))

    with pytest.raises(CommandError, match=REMOVED):
        run_command(Answers(former(gene), promote="y"))


# ------------------------------------------------------- refusals (AC14)
@pytest.mark.parametrize("confirm", ["", "anonymise", "yes", "ANONYMISE please"])
def test_anything_but_the_word_changes_nothing(
    owner: User, gene: User, confirm: str
) -> None:
    mark = audit_mark()

    output = anonymise_command(Typed("gene@example.com", confirm))

    assert "Nothing was changed." in output
    assert fresh(gene).email == "gene@example.com"
    assert audit_mark() == mark


def test_an_unknown_email_changes_nothing(owner: User) -> None:
    with pytest.raises(CommandError, match="No account"):
        anonymise_command(Typed("nobody@example.com"))


def test_the_last_active_admin_is_refused(owner: User) -> None:
    """AC14, as U0.5's `account_last_admin`."""
    with pytest.raises(CommandError, match="At least one Admin must stay active."):
        anonymise_command(Typed("jade@example.com"))

    assert fresh(owner).email == "jade@example.com"


def test_an_admin_who_isnt_the_last_can_be_anonymised(owner: User) -> None:
    second = make_staff("mali", "admin")

    anonymise_command(Typed("mali@example.com"))

    assert fresh(second).email == former(second)


def test_system_is_refused(owner: User) -> None:
    with pytest.raises(CommandError, match="The System account can't be changed."):
        anonymise_command(Typed(SYSTEM_USERNAME))


# ------------------------------------------- the System account (§5.2, §10)
def test_the_services_refuse_to_change_system(owner: User) -> None:
    system = system_account()
    changes: dict[str, Callable[[], object]] = {
        "role": lambda: set_role(owner, system, Role.TECH),
        "reactivate": lambda: reactivate(owner, system),
        "deactivate": lambda: deactivate(owner, system, Reason(LEFT_COMPANY)),
        "password": lambda: give_new_password(owner, system),
        "anonymise": lambda: anonymise(system),
    }

    for name, change in changes.items():
        with refused("account_is_system"):
            change()
        assert fresh(system).is_active is False, name


def test_system_stays_off_even_by_raw_sql(owner: User) -> None:
    with named_in_sql(owner.pk), refused_by("auth_user_system_stays_off"):
        run(
            "UPDATE auth_user SET is_active = true WHERE username = %s",
            [SYSTEM_USERNAME],
        )


@pytest.mark.parametrize("email", ["someone@cucumber.invalid", "X@Cucumber.Invalid"])
def test_the_reserved_domain_cant_be_given_to_staff(owner: User, email: str) -> None:
    with refused("account_email_invalid"):
        add_account(owner, "Someone", email, Role.TECH)


def test_cucumber_admin_refuses_the_reserved_domain(db: None) -> None:
    with pytest.raises(CommandError, match="Enter a whole email address"):
        run_command(Answers("someone@cucumber.invalid"))

    assert not User.objects.filter(username="someone@cucumber.invalid").exists()


# ----------------------------------------------------------- the Staff pages
def test_the_staff_list_hides_system(owner_client: Client) -> None:
    html = text(owner_client.get(STAFF))

    assert SYSTEM_USERNAME not in html
    assert f"{STAFF}{system_id()}/" not in html


def test_an_anonymised_account_shows_as_former_staff_with_no_reactivate(
    owner: User, owner_client: Client, gene: User
) -> None:
    anonymise_command(Typed("gene@example.com"))

    listing = text(owner_client.get(STAFF))
    detail = text(owner_client.get(f"{STAFF}{gene.pk}/"))

    assert f"Former staff #{gene.pk}" in listing
    assert "Deactivated" in detail
    assert f"{STAFF}{gene.pk}/reactivate/" not in detail


def test_reactivating_an_anonymised_account_on_the_page_is_refused(
    owner: User, owner_client: Client, gene: User
) -> None:
    anonymise_command(Typed("gene@example.com"))

    response = owner_client.post(f"{STAFF}{gene.pk}/reactivate/", follow=True)

    assert f"Former staff #{gene.pk}'s {REMOVED}" in text(response)
    assert fresh(gene).is_active is False
