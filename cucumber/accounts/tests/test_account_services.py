"""AC22-AC25, AC27, AC28: the account rules, called directly (design §7.1, §7.3)."""

from collections.abc import Callable
from typing import Any
from unittest import mock

import pytest
from django.contrib.auth.models import AnonymousUser, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError

from cucumber.accounts import services
from cucumber.accounts.services import (
    add_account,
    change_is_due,
    deactivate,
    give_new_password,
    lift_lock,
    new_temporary_password,
    password_chosen,
    reactivate,
    require_admin,
)
from cucumber.accounts.tests.helpers import (
    LOOK_ALIKES,
    TEMPORARY_PASSWORD,
    add_failures,
    change_due,
    failures,
    mark_change_due,
)
from cucumber.core.refusals import message_for
from cucumber.core.tests.rows import run
from cucumber.core.tests.stock import make_staff, refused

pytestmark = pytest.mark.django_db

LONGEST_EMAIL = 150  # auth_user.username's size


def fresh(user: User) -> User:
    return User.objects.get(pk=user.pk)


# --------------------------------------------------------------- messages
@pytest.mark.parametrize(
    ("rule", "message"),
    [
        ("account_email_taken", "Another account already uses this email."),
        (
            "account_email_invalid",
            "Enter a whole email address, like name@example.com.",
        ),
        ("account_cannot_deactivate_self", "You can't deactivate your own account."),
        ("account_cannot_reset_self", "Change your own password on the Password page."),
        ("account_last_admin", "At least one Admin must stay active."),
        (
            "password_same_as_temporary",
            "Choose a password different from the one you were given.",
        ),
    ],
)
def test_staff_see_the_designed_message(rule: str, message: str) -> None:
    assert message_for(rule) == message


# ----------------------------------------------------------- AC28 admin
def test_require_admin_lets_the_admin_through(owner: User) -> None:
    require_admin(owner)


def test_require_admin_refuses_anyone_else(gene: User) -> None:
    with pytest.raises(PermissionDenied):
        require_admin(gene)
    with pytest.raises(PermissionDenied):
        require_admin(AnonymousUser())


ADMIN_ONLY: list[Callable[[User, User], Any]] = [
    deactivate,
    reactivate,
    give_new_password,
    lift_lock,
    lambda by, _: add_account(by, "Mali", "mali@example.com"),
]


@pytest.mark.parametrize("action", ADMIN_ONLY)
def test_a_tech_can_reach_no_account_change(
    action: Callable[[User, User], Any], gene: User, pim: User
) -> None:
    before = (fresh(pim).is_active, fresh(pim).password, User.objects.count())

    with pytest.raises(PermissionDenied):
        action(gene, pim)

    assert (fresh(pim).is_active, fresh(pim).password, User.objects.count()) == before


# ---------------------------------------------------------- AC22 add one
def test_adding_an_account_stores_the_email_as_its_user_name(owner: User) -> None:
    added = add_account(owner, "Mali", "  Mali@Example.COM ")

    account = fresh(added.account)
    assert account.username == "mali@example.com"
    assert account.email == "mali@example.com"
    assert account.first_name == "Mali"
    assert account.last_name == ""
    assert account.is_active
    assert not account.is_staff and not account.is_superuser


def test_a_new_account_has_no_role_yet(owner: User) -> None:
    """Roles come in U0.6 (spec AC22)."""
    added = add_account(owner, "Mali", "mali@example.com")

    assert not fresh(added.account).groups.exists()


def test_a_new_account_gets_a_working_temporary_password_it_must_change(
    owner: User,
) -> None:
    added = add_account(owner, "Mali", "mali@example.com")

    assert TEMPORARY_PASSWORD.fullmatch(added.password)
    assert fresh(added.account).check_password(added.password)
    assert change_due(added.account)
    assert change_is_due(added.account)


@pytest.mark.parametrize("taken", ["gene@example.com", " GENE@example.com"])
def test_an_email_can_belong_to_one_account_only(
    owner: User, gene: User, taken: str
) -> None:
    count = User.objects.count()

    with refused("account_email_taken"):
        add_account(owner, "Gene again", taken)

    assert User.objects.count() == count


@pytest.mark.parametrize(
    "email",
    [
        "",
        "   ",
        "mali",
        "mali@",
        "@example.com",
        "mali@example",
        "mali @example.com",
        "m" * (LONGEST_EMAIL - len("@example.com") + 1) + "@example.com",
    ],
)
def test_a_broken_or_too_long_email_is_refused(owner: User, email: str) -> None:
    count = User.objects.count()

    with refused("account_email_invalid"):
        add_account(owner, "Mali", email)

    assert User.objects.count() == count


def test_a_150_character_email_fits(owner: User) -> None:
    email = "m" * (LONGEST_EMAIL - len("@example.com")) + "@example.com"

    added = add_account(owner, "Mali", email)

    assert fresh(added.account).username == email


# ----------------------------------------------------- AC23, AC24 on/off
def test_deactivate_switches_an_account_off_and_keeps_it(
    owner: User, gene: User
) -> None:
    deactivate(owner, gene)

    assert not fresh(gene).is_active


def test_reactivate_switches_it_back_on(owner: User, gene: User) -> None:
    deactivate(owner, gene)

    reactivate(owner, gene)

    assert fresh(gene).is_active


def test_the_admin_cannot_deactivate_themselves(owner: User) -> None:
    with refused("account_cannot_deactivate_self"):
        deactivate(owner, owner)

    assert fresh(owner).is_active


# ---------------------------------------------------- AC25 new password
def test_a_new_password_works_and_must_be_changed(owner: User, gene: User) -> None:
    old_hash = fresh(gene).password

    password = give_new_password(owner, gene)

    assert TEMPORARY_PASSWORD.fullmatch(password)
    assert fresh(gene).password != old_hash
    assert fresh(gene).check_password(password)
    assert change_due(gene)


def test_giving_a_new_password_twice_keeps_one_change_due_row(
    owner: User, gene: User
) -> None:
    give_new_password(owner, gene)

    second = give_new_password(owner, gene)

    assert fresh(gene).check_password(second)
    assert change_due(gene)


def test_a_new_password_and_its_change_due_mark_are_saved_together(
    owner: User, gene: User
) -> None:
    """If the mark can't be saved, the password isn't changed either (§7.1)."""
    old_hash = fresh(gene).password
    run(
        "CREATE FUNCTION refuse_mark() RETURNS trigger LANGUAGE plpgsql AS"
        " $$ BEGIN RAISE EXCEPTION 'test: mark refused'; END $$;"
        " CREATE TRIGGER refuse_mark BEFORE INSERT ON accounts_password_change_due"
        " FOR EACH ROW EXECUTE FUNCTION refuse_mark();"
    )

    with pytest.raises(DatabaseError):
        give_new_password(owner, gene)

    assert fresh(gene).password == old_hash


def test_the_admin_changes_their_own_password_on_the_password_page(
    owner: User,
) -> None:
    old_hash = fresh(owner).password

    with refused("account_cannot_reset_self"):
        give_new_password(owner, owner)

    assert fresh(owner).password == old_hash
    assert not change_due(owner)


def test_choosing_a_password_clears_the_change_due(gene: User) -> None:
    mark_change_due(gene)

    password_chosen(gene)

    assert not change_due(gene)
    assert not change_is_due(gene)


# ------------------------------------------------------------ AC11 lock
def test_lifting_a_lock_clears_that_accounts_failures_only(
    owner: User, gene: User
) -> None:
    add_failures("gene@example.com", 5)
    add_failures("pim@example.com", 5)

    lift_lock(owner, gene)

    assert failures("gene@example.com") == 0
    assert failures("pim@example.com") == 5


# ---------------------------------------------- AC27 temporary passwords
def test_temporary_passwords_use_no_look_alike_characters(gene: User) -> None:
    passwords = {new_temporary_password(gene) for _ in range(200)}

    assert len(passwords) == 200, "repeated: not random enough"
    for password in passwords:
        assert TEMPORARY_PASSWORD.fullmatch(password), password
        assert not set(password) & LOOK_ALIKES


def test_temporary_passwords_pass_djangos_four_rules(gene: User) -> None:
    for _ in range(50):
        validate_password(new_temporary_password(gene), user=gene)


def test_a_temporary_password_that_fails_a_rule_is_made_again(gene: User) -> None:
    """E.g. one that happens to look too like the person's email (§7.3)."""
    calls = iter([ValidationError("too similar"), None])

    def first_fails(password: str, user: User | None = None) -> None:
        outcome = next(calls)
        if outcome is not None:
            raise outcome

    # services.py calls Django's validate_password by that name (§7.3).
    with mock.patch.object(
        services, "validate_password", side_effect=first_fails, create=True
    ):
        password = new_temporary_password(gene)

    assert TEMPORARY_PASSWORD.fullmatch(password)
    assert next(calls, "used both") == "used both"


# ------------------------------------------------------ G4 review (M2, M8)
def test_the_last_active_admin_cannot_be_deactivated(owner: User) -> None:
    """Two Admins switching each other off would leave nobody on Staff (G4 M2).

    `mali` is a stale copy: the page Mali pressed from was drawn before the
    Owner switched Mali off, or both pressed at the same moment.
    """
    mali = make_staff("mali", "admin")
    deactivate(owner, mali)

    with refused("account_last_admin"):
        deactivate(mali, owner)

    assert fresh(owner).is_active


def test_one_admin_may_deactivate_another_while_one_stays(owner: User) -> None:
    mali = make_staff("mali", "admin")

    deactivate(owner, mali)

    assert not fresh(mali).is_active


def test_an_email_added_by_someone_else_a_moment_ago_is_refused(
    owner: User, gene: User
) -> None:
    """The look-up said free, then the database said taken (G4 M8)."""
    count = User.objects.count()

    with (
        # The Admin check uses exists() too, so it is answered separately.
        mock.patch.object(services, "has_role", return_value=True),
        mock.patch("django.db.models.query.QuerySet.exists", return_value=False),
        refused("account_email_taken"),
    ):
        add_account(owner, "Gene again", "gene@example.com")

    assert User.objects.count() == count
