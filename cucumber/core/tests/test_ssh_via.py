"""G4 review #3: an SSH command's audit rows say who ran it and from where.

The System account stands for every SSH command, so `via` carries the rest:
`<command> by <ssh user> (ssh <SSH_CONNECTION>)`. The container doesn't know
the person, so the runbook and `scripts/flag.py` pass `SSH_USER` and
`SSH_CONNECTION` in.
"""

from io import StringIO

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from waffle.models import Flag

from cucumber.core.audit import ssh_via
from cucumber.core.tests.rows import as_system
from cucumber.core.tests.trail import audit_mark, only_row

pytestmark = pytest.mark.django_db

CONNECTION = "203.0.113.5 52211 10.0.0.2 22"


@pytest.fixture
def over_ssh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SSH_USER", "sawat")
    monkeypatch.setenv("SSH_CONNECTION", CONNECTION)


def test_via_names_the_command_the_user_and_the_connection(over_ssh: None) -> None:
    assert ssh_via("cucumber_flag") == f"cucumber_flag by sawat (ssh {CONNECTION})"


def test_without_ssh_it_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SSH_USER", "sawat")
    monkeypatch.delenv("SSH_CONNECTION", raising=False)

    assert ssh_via("cucumber_flag") == "cucumber_flag by sawat (no ssh connection)"


def test_without_a_user_it_falls_back_to_the_process_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SSH_USER", raising=False)
    monkeypatch.delenv("SSH_CONNECTION", raising=False)

    assert ssh_via("cucumber_flag").startswith("cucumber_flag by ")


def test_control_characters_in_the_environment_are_dropped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SSH_USER", "sa\nwat\x1b[31m")
    monkeypatch.setenv("SSH_CONNECTION", "1.2.3.4 5 6 7\r\n")

    assert ssh_via("x") == "x by sawat[31m (ssh 1.2.3.4 5 6 7)"


def test_the_flag_command_writes_it(over_ssh: None) -> None:
    with as_system():
        Flag.objects.create(name="probe", everyone=False, superusers=False)
        Group.objects.get_or_create(name="admin")
    mark = audit_mark()

    call_command("cucumber_flag", "probe", "on", stdout=StringIO())

    assert only_row(mark, "waffle_flag").via == (
        f"cucumber_flag by sawat (ssh {CONNECTION})"
    )
