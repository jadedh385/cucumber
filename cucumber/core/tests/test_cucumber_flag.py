"""AC13: `cucumber_flag` switches a flag with fixed meanings (U0.4a design §7).

Flags are made here the way a feature's migration makes them: every field
off. Then each starts "messy", as a hand edit could leave it, to prove the
command sets every field, not only the one it is about. Waffle's per-user list
is left alone: nothing in Cucumber can fill it (no admin), and `cucumber_app`
may only read it (design §7). That the command works as `cucumber_app` is in
test_flag_grants.py.
"""

import re
from decimal import Decimal
from io import StringIO
from typing import Any

import pytest
from django.contrib.auth.models import AnonymousUser, Group, User
from django.core.management import CommandError, call_command
from django.test import RequestFactory, override_settings
from waffle import flag_is_active
from waffle.models import Flag

from cucumber.accounts.permissions import Role
from cucumber.accounts.services import replace_role
from cucumber.core.tests.rows import staff_email
from cucumber.core.tests.trail import as_system

pytestmark = pytest.mark.django_db

# Waffle types its Flag model as the abstract base, which lacks the groups.
FlagRow = Any

ALWAYS_OFF = {
    "superusers": False,
    "staff": False,
    "authenticated": False,
    "testing": False,
    "rollout": False,
    "percent": None,
    "languages": "",
}


def cucumber_flag(*args: str) -> str:
    out = StringIO()
    call_command("cucumber_flag", *args, stdout=out)
    return out.getvalue()


def make_flag(name: str) -> FlagRow:
    """A flag as a feature's migration makes it: every field off."""
    with as_system():
        return Flag.objects.create(name=name, everyone=False, superusers=False)


def make_messy_flag(name: str) -> FlagRow:
    """A flag with every other Waffle switch set, and a group."""
    with as_system():
        flag: FlagRow = Flag.objects.create(
            name=name,
            everyone=None,
            superusers=True,
            staff=True,
            authenticated=True,
            testing=True,
            rollout=True,
            percent=Decimal("50.0"),
            languages="th",
        )
        flag.groups.add(Group.objects.get_or_create(name="supervisor")[0])
    return flag


def assert_only(flag_name: str, everyone: bool | None, groups: set[str]) -> None:
    flag: FlagRow = Flag.objects.get(name=flag_name)
    assert flag.everyone is everyone
    assert {group.name for group in flag.groups.all()} == groups
    for field, off in ALWAYS_OFF.items():
        assert getattr(flag, field) == off, field


@pytest.fixture
def owner_group() -> Group:
    return Group.objects.get_or_create(name="admin")[0]


# --------------------------------------------------------------- switching
def test_on_is_on_for_everyone_and_nothing_else(owner_group: Group) -> None:
    make_messy_flag("needs_attention")

    cucumber_flag("needs_attention", "on")

    assert_only("needs_attention", everyone=True, groups=set())


def test_off_is_off_for_everyone_and_nothing_else(owner_group: Group) -> None:
    make_messy_flag("needs_attention")

    cucumber_flag("needs_attention", "off")

    assert_only("needs_attention", everyone=False, groups=set())


def test_on_for_groups_lets_the_groups_decide(owner_group: Group) -> None:
    make_messy_flag("needs_attention")

    cucumber_flag("needs_attention", "on", "--group", "admin", "--group", "supervisor")

    assert_only("needs_attention", everyone=None, groups={"admin", "supervisor"})


def test_naming_groups_again_replaces_the_old_ones(owner_group: Group) -> None:
    make_messy_flag("needs_attention")
    cucumber_flag("needs_attention", "on", "--group", "supervisor")

    cucumber_flag("needs_attention", "on", "--group", "admin")

    assert_only("needs_attention", everyone=None, groups={"admin"})


def test_each_change_is_reported_in_one_line(owner_group: Group) -> None:
    make_flag("needs_attention")

    output = cucumber_flag("needs_attention", "on", "--group", "admin")

    assert output.strip() == "needs_attention is now on for: admin"


# ---------------------------------------------------------------- refusals
def test_an_unknown_flag_is_refused_and_not_created() -> None:
    make_flag("needs_attention")
    make_flag("discord_alerts")

    with pytest.raises(CommandError) as refused:
        cucumber_flag("needs_atention", "on")

    message = str(refused.value)
    assert message.startswith("No flag called needs_atention.")
    assert "Flags on local: discord_alerts, needs_attention" in message
    assert Flag.objects.count() == 2


def test_an_unknown_group_is_refused_and_nothing_changes(owner_group: Group) -> None:
    make_flag("needs_attention")

    with pytest.raises(CommandError, match="No group called Owners"):
        cucumber_flag("needs_attention", "on", "--group", "Owners")

    assert_only("needs_attention", everyone=False, groups=set())


def test_off_with_a_group_is_refused(owner_group: Group) -> None:
    make_flag("needs_attention")

    with pytest.raises(CommandError, match="off"):
        cucumber_flag("needs_attention", "off", "--group", "admin")


def test_a_flag_name_needs_on_or_off() -> None:
    make_flag("needs_attention")

    with pytest.raises(CommandError, match="on or off"):
        cucumber_flag("needs_attention")


# -------------------------------------------------------------------- list
@override_settings(ENVIRONMENT="production")
def test_list_shows_every_flag_and_who_it_is_on_for(owner_group: Group) -> None:
    make_flag("discord_alerts")
    make_flag("needs_attention")
    make_flag("print_labels")
    cucumber_flag("needs_attention", "on", "--group", "admin")
    cucumber_flag("print_labels", "on")

    lines = cucumber_flag("list").splitlines()

    assert lines[0] == "Flags on production"
    assert re.fullmatch(r"\s+discord_alerts\s+off", lines[1])
    assert re.fullmatch(r"\s+needs_attention\s+on for: admin", lines[2])
    assert re.fullmatch(r"\s+print_labels\s+on", lines[3])
    assert len(lines) == 4


# ---------------------------------------------------- seen on the next page
def test_a_change_shows_on_the_very_next_page_load(owner_group: Group) -> None:
    make_flag("needs_attention")
    email = staff_email("jade")
    with as_system():
        owner = User.objects.create_user(username=email, email=email)
        replace_role(owner, Role.ADMIN)
    page = RequestFactory().get("/")
    page.user = owner
    other_page = RequestFactory().get("/")
    other_page.user = AnonymousUser()

    assert not flag_is_active(page, "needs_attention")
    cucumber_flag("needs_attention", "on", "--group", "admin")
    assert flag_is_active(page, "needs_attention")
    assert not flag_is_active(other_page, "needs_attention")
    cucumber_flag("needs_attention", "off")
    assert not flag_is_active(page, "needs_attention")
