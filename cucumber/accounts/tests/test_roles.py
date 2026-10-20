"""AC1, AC2, AC4–AC7: the four roles, one per account, given and taken away.

Migrations `0005_roles` and `0006_one_role` (design §6), `set_role` (§5.1),
adding an account with a role (§5.2), the last Admin (§5.3), `standing` and
`require` (§4.1) and the role log lines (§9).
"""

import importlib
import logging
from types import ModuleType
from typing import Any
from unittest import mock

import pytest
from django.apps import apps
from django.contrib.auth.models import AnonymousUser, Group, User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from waffle.models import Flag

from cucumber.accounts import services
from cucumber.accounts.permissions import (
    NotAllowed,
    Permission,
    Role,
    Standing,
    require,
    standing,
)
from cucumber.accounts.services import add_account, deactivate, role_of, set_role
from cucumber.core.refusals import Refused
from cucumber.core.tests.rows import fetch_all, fetch_one, refused_by, run
from cucumber.core.tests.stock import make_staff, not_allowed, refused
from cucumber.events.tests.test_concurrency import at_the_same_moment

pytestmark = pytest.mark.django_db

ONE_ROLE = "auth_user_one_role"
ROLE_NAMES = {"admin", "supervisor", "tech", "read_only"}
ACTIVE_ADMINS = (
    "SELECT count(*) FROM auth_user u"
    " JOIN auth_user_groups ug ON ug.user_id = u.id"
    " JOIN auth_group g ON g.id = ug.group_id"
    " WHERE g.name = 'admin' AND u.is_active"
)


def migration(name: str) -> ModuleType:
    return importlib.import_module(f"cucumber.accounts.migrations.{name}")


def seed_roles() -> None:
    """The groups the migrations made, for a test whose database was flushed."""
    for name in ROLE_NAMES:
        Group.objects.get_or_create(name=name)


def roles_of(user: User) -> list[str]:
    return sorted(User.objects.get(pk=user.pk).groups.values_list("name", flat=True))


# --------------------------------------------------------------- AC1
def test_the_four_roles_exist_after_migrating() -> None:
    assert set(Group.objects.values_list("name", flat=True)) >= ROLE_NAMES


def test_adding_the_roles_twice_still_leaves_one_of_each() -> None:
    add_roles = migration("0005_roles").add_roles

    add_roles(apps, None)
    add_roles(apps, None)

    for name in ROLE_NAMES:
        assert Group.objects.filter(name=name).count() == 1


@pytest.mark.parametrize("role", ["supervisor", "tech", "read_only"])
def test_undoing_the_roles_is_refused_while_anyone_holds_one(role: str) -> None:
    """Dropping a group would silently take people's roles away (§6.1)."""
    make_staff("gene", role)

    with pytest.raises(RuntimeError, match=r"\b1\b.*(account|role)"):
        migration("0005_roles").remove_roles(apps, None)

    assert Group.objects.filter(name=role).exists()


def test_undoing_the_roles_is_refused_while_a_flag_is_on_for_one() -> None:
    """Deleting the group would silently drop it from the flag (§6.1)."""
    flag: Any = Flag.objects.create(name="needs_attention")  # waffle is untyped
    flag.groups.add(Group.objects.get(name="supervisor"))

    with pytest.raises(RuntimeError, match="flag"):
        migration("0005_roles").remove_roles(apps, None)

    assert Group.objects.filter(name="supervisor").exists()


def test_undoing_the_roles_removes_the_three_and_keeps_admin() -> None:
    make_staff("jade", "admin")

    migration("0005_roles").remove_roles(apps, None)

    names = set(Group.objects.values_list("name", flat=True))
    assert "admin" in names
    assert not names & {"supervisor", "tech", "read_only"}


# --------------------------------------------------------------- AC2
def test_one_role_per_account_is_a_database_rule() -> None:
    [definition] = [
        str(row[0])
        for row in fetch_all(
            "SELECT indexdef FROM pg_indexes WHERE indexname = %s", [ONE_ROLE]
        )
    ]

    assert "UNIQUE" in definition
    assert "auth_user_groups" in definition
    assert definition.endswith("(user_id)")


def test_a_second_role_written_straight_into_the_table_is_refused(
    gene: User,
) -> None:
    supervisor = Group.objects.get(name="supervisor")

    with refused_by(ONE_ROLE):
        run(
            "INSERT INTO auth_user_groups (user_id, group_id) VALUES (%s, %s)",
            [gene.pk, supervisor.pk],
        )

    assert roles_of(gene) == ["tech"]


def test_the_pre_check_names_accounts_with_two_roles_or_an_unmatched_email() -> None:
    """Instead of a raw index error at G5 on staging or production (§6.2, §8)."""
    run(f"DROP INDEX IF EXISTS {ONE_ROLE}")
    two = make_staff("gene", "tech")
    User.groups.through.objects.create(
        user=two, group=Group.objects.get_or_create(name="supervisor")[0]
    )
    # Passes the auth_user rule (lowercase, trimmed) but isn't its NFKC key.
    # objects.create, not create_user: that one NFKCs the user name itself.
    wide = "ｐｉｍ@example.com"
    User.objects.create(username=wide, email=wide)
    make_staff("mali", "tech")

    with pytest.raises(RuntimeError) as caught:
        migration("0006_one_role").refuse_bad_accounts(apps, None)

    assert "gene@example.com" in str(caught.value)
    assert wide in str(caught.value)
    assert "mali@example.com" not in str(caught.value)


def test_the_pre_check_names_accounts_in_a_group_that_is_not_a_role() -> None:
    """Every group is a role (Q1); an old one, like a flag's `Owner`, isn't (G4 M1)."""
    make_staff("gene", "Owner")
    make_staff("mali", "tech")

    with pytest.raises(RuntimeError) as caught:
        migration("0006_one_role").refuse_bad_accounts(apps, None)

    assert "gene@example.com (Owner)" in str(caught.value)
    assert "mali@example.com" not in str(caught.value)


def test_the_pre_check_passes_when_every_account_is_fine() -> None:
    make_staff("gene", "tech")
    make_staff("pim", None)

    migration("0006_one_role").refuse_bad_accounts(apps, None)


# ------------------------------------------------------------ set_role (AC4)
@pytest.mark.parametrize("role", list(Role), ids=str)
def test_giving_a_role_replaces_the_old_one(
    owner: User, gene: User, role: Role
) -> None:
    set_role(owner, gene, role)

    assert roles_of(gene) == [str(role)]


def test_a_role_can_be_removed(owner: User, gene: User) -> None:
    set_role(owner, gene, None)

    assert roles_of(gene) == []


def test_an_account_without_a_role_can_be_given_one(owner: User) -> None:
    mali = make_staff("mali", None)

    set_role(owner, mali, Role.SUPERVISOR)

    assert roles_of(mali) == ["supervisor"]


def test_a_group_that_is_not_a_role_reads_as_no_role(owner: User) -> None:
    """Like `standing`, never a crash (G4 M1), and a new role replaces it."""
    pim = make_staff("pim", "Owner")

    assert role_of(pim) is None
    set_role(owner, pim, Role.TECH)

    assert roles_of(pim) == ["tech"]


def test_a_deactivated_account_keeps_its_role(owner: User, gene: User) -> None:
    """Q3: switching it back on returns it as it was."""
    deactivate(owner, gene)

    assert roles_of(gene) == ["tech"]


@pytest.mark.parametrize("role", ["supervisor", "tech", "read_only", None])
def test_only_someone_who_manages_users_may_give_a_role(
    owner: User, gene: User, role: str | None
) -> None:
    """AC8, called directly."""
    by = make_staff(f"by_{role or 'none'}", role)

    with not_allowed("role_not_allowed"):
        set_role(by, gene, Role.ADMIN)

    assert roles_of(gene) == ["tech"]
    assert roles_of(by) == ([role] if role else [])


def test_a_switched_off_admin_may_not_give_a_role(owner: User, gene: User) -> None:
    mali = make_staff("mali", "admin")
    User.objects.filter(pk=mali.pk).update(is_active=False)

    with not_allowed("account_not_active"):
        set_role(mali, gene, Role.ADMIN)

    assert roles_of(gene) == ["tech"]


# --------------------------------------------------------------- AC7
def test_nobody_changes_their_own_role(owner: User) -> None:
    make_staff("mali", "admin")

    with refused("account_cannot_change_own_role"):
        set_role(owner, owner, Role.TECH)

    assert roles_of(owner) == ["admin"]


def test_one_admin_may_change_another_while_one_stays(owner: User) -> None:
    mali = make_staff("mali", "admin")

    set_role(owner, mali, Role.SUPERVISOR)

    assert roles_of(mali) == ["supervisor"]


def test_a_switched_off_admin_s_role_may_be_removed(owner: User) -> None:
    """A deactivated Admin isn't counted as an Admin (§5.3)."""
    mali = make_staff("mali", "admin")
    User.objects.filter(pk=mali.pk).update(is_active=False)

    set_role(owner, mali, None)

    assert roles_of(mali) == []


# ------------------------------------------------------ AC4: adding with a role
@pytest.mark.parametrize("role", list(Role), ids=str)
def test_a_new_account_gets_the_role_it_was_added_with(owner: User, role: Role) -> None:
    added = add_account(owner, "Mali", "mali@example.com", role)

    assert roles_of(added.account) == [str(role)]


def test_a_new_account_needs_a_role(owner: User) -> None:
    count = User.objects.count()

    with refused("account_role_required"):
        add_account(owner, "Mali", "mali@example.com", None)

    assert User.objects.count() == count


# --------------------------------------------------------- standing (§4.1)
def test_standing_reads_the_role_and_the_active_flag(gene: User) -> None:
    assert standing(gene) == Standing(gene.pk, True, Role.TECH)


def test_standing_of_someone_without_a_role() -> None:
    mali = make_staff("mali", None)

    assert standing(mali) == Standing(mali.pk, True, None)


def test_standing_of_someone_signed_out() -> None:
    assert standing(AnonymousUser()) == Standing(None, False, None)


def test_standing_reads_the_database_not_the_copy_it_is_given(gene: User) -> None:
    """A session still open after a change can't act on the old standing (AC5)."""
    stale = User.objects.get(pk=gene.pk)
    User.objects.filter(pk=gene.pk).update(is_active=False)
    User.groups.through.objects.filter(user_id=gene.pk).delete()

    assert standing(stale) == Standing(gene.pk, False, None)


def test_standing_is_one_query(gene: User) -> None:
    with CaptureQueriesContext(connection) as queries:
        standing(gene)

    assert len(queries.captured_queries) == 1


def test_require_hands_back_the_standing(owner: User) -> None:
    assert require(owner, Permission.MANAGE_USERS) == Standing(
        owner.pk, True, Role.ADMIN
    )


def test_require_refuses_someone_signed_out() -> None:
    with not_allowed("account_not_active"):
        require(AnonymousUser(), Permission.OWN_ACCOUNT)


def test_require_refuses_a_switched_off_account_before_its_role(gene: User) -> None:
    User.objects.filter(pk=gene.pk).update(is_active=False)

    with not_allowed("account_not_active"):
        require(gene, Permission.LOG_WORK)


def test_require_refuses_a_role_the_row_does_not_allow(gene: User) -> None:
    with not_allowed("role_not_allowed"):
        require(gene, Permission.MANAGE_USERS)


def test_a_refusal_by_role_carries_its_message_and_is_no_refused(gene: User) -> None:
    with pytest.raises(NotAllowed) as caught:
        require(gene, Permission.MANAGE_USERS)

    assert caught.value.message == "Your role can't do this."
    assert not isinstance(caught.value, Refused)


# --------------------------------------------------------------- AC6
def test_a_role_change_writes_one_log_line(
    owner: User, gene: User, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="cucumber.accounts")

    set_role(owner, gene, Role.SUPERVISOR)
    set_role(owner, gene, None)

    assert caplog.messages == [
        f"role changed account={gene.pk} from=tech to=supervisor by={owner.pk}",
        f"role changed account={gene.pk} from=supervisor to=none by={owner.pk}",
    ]


def test_giving_the_same_role_again_changes_nothing_and_logs_nothing(
    owner: User, gene: User, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="cucumber.accounts")

    set_role(owner, gene, Role.TECH)

    assert roles_of(gene) == ["tech"]
    assert caplog.messages == []


def test_adding_an_account_logs_its_role_after_it(
    owner: User, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="cucumber.accounts")

    added = add_account(owner, "Mali", "mali@example.com", Role.TECH)

    pk = added.account.pk
    assert caplog.messages == [
        f"account added account={pk} by={owner.pk}",
        f"role changed account={pk} from=none to=tech by={owner.pk}",
    ]


# ------------------------------------- AC7: the last Admin, step by step
def test_the_last_active_admin_keeps_the_role_even_past_a_stale_check(
    owner: User,
) -> None:
    """The check made after the locks, not only the one at the door (§5.1).

    Mali passed the Admin check a moment ago (a stale page, or two Admins at
    once) and has since lost the role: the Owner is now the last Admin.
    """
    mali = make_staff("mali", "tech")
    stale = Standing(mali.pk, True, Role.ADMIN)

    with (
        mock.patch("cucumber.accounts.services.require", return_value=stale),
        refused("account_last_admin"),
    ):
        set_role(mali, owner, Role.TECH)

    assert roles_of(owner) == ["admin"]


def test_the_last_active_admin_is_not_deactivated_past_a_stale_check(
    owner: User,
) -> None:
    mali = make_staff("mali", "tech")
    stale = Standing(mali.pk, True, Role.ADMIN)

    with (
        mock.patch("cucumber.accounts.services.require", return_value=stale),
        refused("account_last_admin"),
    ):
        deactivate(mali, owner)

    assert User.objects.get(pk=owner.pk).is_active


def lose_admin_while_waiting(admin: User) -> Any:
    """`lock_for_account_change` that, once it has the locks, finds `admin`
    demoted: another Admin's change committed while this one waited."""
    real = services.lock_for_account_change

    def lock(account: User) -> None:
        real(account)
        services.replace_role(admin, Role.TECH)

    return mock.patch("cucumber.accounts.services.lock_for_account_change", lock)


@pytest.mark.parametrize(
    "change",
    [
        lambda by, account: set_role(by, account, Role.ADMIN),
        lambda by, account: deactivate(by, account),
    ],
    ids=["set_role", "deactivate"],
)
def test_an_admin_demoted_while_waiting_for_the_locks_changes_nothing(
    owner: User, gene: User, change: Any
) -> None:
    """The Admin's own role is read again under the locks (G4 L1)."""
    mali = make_staff("mali", "admin")

    with lose_admin_while_waiting(mali), not_allowed():
        change(mali, gene)

    gene = User.objects.get(pk=gene.pk)
    assert roles_of(gene) == ["tech"]
    assert gene.is_active


# ------------------------------------------------- AC7: two Admins at once
@pytest.mark.django_db(transaction=True)
def test_two_admins_demoting_each_other_at_once_leave_one_admin() -> None:
    """Taken one at a time, in the same lock order, so neither waits forever."""
    seed_roles()
    jade = make_staff("jade", "admin")
    mali = make_staff("mali", "admin")

    results = at_the_same_moment(
        [
            lambda: set_role(jade, mali, Role.TECH),
            lambda: set_role(mali, jade, Role.TECH),
        ]
    )

    refusals = [result for result in results if isinstance(result, Exception)]
    assert len(refusals) == 1, results
    assert getattr(refusals[0], "rule", None) in {
        "account_last_admin",
        "role_not_allowed",
    }
    assert fetch_one(ACTIVE_ADMINS) == (1,)


@pytest.mark.django_db(transaction=True)
def test_deactivating_and_demoting_each_other_at_once_leave_one_admin() -> None:
    seed_roles()
    jade = make_staff("jade", "admin")
    mali = make_staff("mali", "admin")

    results = at_the_same_moment(
        [
            lambda: deactivate(jade, mali),
            lambda: set_role(mali, jade, Role.TECH),
        ]
    )

    refusals = [result for result in results if isinstance(result, Exception)]
    assert len(refusals) == 1, results
    assert getattr(refusals[0], "rule", None) in {
        "account_last_admin",
        "account_not_active",
        "role_not_allowed",
    }, results
    assert fetch_one(ACTIVE_ADMINS) == (1,)
