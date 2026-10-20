"""AC9: `cucumber_audit`, the Admin's way to read the trail (design §7.1).

The rows are written by hand with fixed times (the stamp trigger is off for
that one insert), so the filters and Bangkok times can be checked exactly.
"""

import json
from io import StringIO

import pytest
from django.contrib.auth.models import Group, User
from django.core.management import CommandError, call_command
from waffle.models import Flag

from cucumber.core.tests.rows import insert, run
from cucumber.core.tests.stock import make_staff
from cucumber.core.tests.trail import LEFT_COMPANY, as_system, audit_mark, system_id

pytestmark = pytest.mark.django_db

# 23:30 on the 19th in Bangkok, and three times on the 20th (UTC+7).
LATE_ON_19TH = "2026-10-19T16:30:00+00:00"
JUST_AFTER_MIDNIGHT = "2026-10-19T17:30:00+00:00"
AFTERNOON = "2026-10-20T07:05:00+00:00"
LATER = "2026-10-20T07:10:00+00:00"


def audit_row_at(at: str, **values: object) -> None:
    """An audit row written at `at`: the stamp trigger is off for this insert."""
    row = {"before": None, "after": None, "reason_code": None, "note": None} | values
    for column in ("before", "after"):
        if row[column] is not None:
            row[column] = json.dumps(row[column])
    run("SET CONSTRAINTS ALL IMMEDIATE")
    run("ALTER TABLE audit_log DISABLE TRIGGER USER")
    insert("audit_log", {"at": at, "db_user": "cucumber_app", **row})
    run("ALTER TABLE audit_log ENABLE TRIGGER USER")
    run("SET CONSTRAINTS ALL DEFERRED")


@pytest.fixture
def people() -> tuple[User, User]:
    """Jade (Admin) and Mali (Tech)."""
    with as_system():
        return make_staff("jade", "admin"), make_staff("mali", "tech")


@pytest.fixture
def trail(people: tuple[User, User]) -> dict[str, int]:
    """Four rows: Jade changes Mali twice and gives a role; System switches a flag."""
    jade, mali = people
    with as_system():
        flag = Flag.objects.create(name="lab_screens")
    tech = Group.objects.get(name="tech")
    audit_row_at(
        LATE_ON_19TH,
        actor_id=jade.pk, table_name="auth_user", row_pk=str(mali.pk),
        action="update", before={"is_staff": False}, after={"is_staff": True},
        via="app",
    )  # fmt: skip
    audit_row_at(
        JUST_AFTER_MIDNIGHT,
        actor_id=jade.pk, table_name="auth_user", row_pk=str(mali.pk),
        action="update", before={"is_active": True}, after={"is_active": False},
        reason_code=LEFT_COMPANY, note="moved to Chiang Mai", via="app",
    )  # fmt: skip
    audit_row_at(
        AFTERNOON,
        actor_id=system_id(), table_name="waffle_flag", row_pk=str(flag.pk),
        action="update", before={"everyone": None}, after={"everyone": True},
        via="cucumber_flag",
    )  # fmt: skip
    audit_row_at(
        LATER,
        actor_id=jade.pk, table_name="auth_user_groups", row_pk=str(mali.pk),
        action="insert", after={"user_id": mali.pk, "group_id": tech.pk}, via="app",
    )  # fmt: skip
    return {"jade": jade.pk, "mali": mali.pk, "flag": flag.pk}


def cucumber_audit(*args: str) -> list[str]:
    out = StringIO()
    call_command("cucumber_audit", *args, stdout=out)
    return [line for line in out.getvalue().splitlines() if line.strip()]


def times(lines: list[str]) -> list[str]:
    """The Bangkok time each row starts with, in the order shown."""
    return [line[:16] for line in lines if line[:4] == "2026"]


# ------------------------------------------------------------ reading
def test_rows_are_newest_first_in_bangkok_time(trail: dict[str, int]) -> None:
    lines = cucumber_audit()

    assert times(lines) == [
        "2026-10-20 14:10",
        "2026-10-20 14:05",
        "2026-10-20 00:30",
        "2026-10-19 23:30",
    ]
    assert lines[-1] == "4 of 4 rows"


def test_a_change_shows_who_how_what_and_why(trail: dict[str, int]) -> None:
    lines = cucumber_audit("--table", "auth_user", "--since", "2026-10-20")

    [row, reason, _total] = lines
    for part in (
        f"#{trail['jade']} (app)",
        f"auth_user {trail['mali']}",
        "update",
        "is_active: true → false",
    ):
        assert part in row
    assert reason.strip() == f'reason: {LEFT_COMPANY} "moved to Chiang Mai"'


def test_system_is_shown_by_name_with_the_command(trail: dict[str, int]) -> None:
    lines = cucumber_audit("--table", "waffle_flag")

    assert "System (cucumber_flag)" in lines[0]
    assert "everyone: null → true" in lines[0]


def test_flags_and_roles_are_shown_by_name(trail: dict[str, int]) -> None:
    """Review L2: one flag's or one account's history reads as one story."""
    flag_line = cucumber_audit("--table", "waffle_flag")[0]
    role_line = cucumber_audit("--table", "auth_user_groups")[0]

    assert "waffle_flag lab_screens" in flag_line
    assert "group_id: tech" in role_line


def test_no_name_or_email_is_ever_shown(trail: dict[str, int]) -> None:
    """AC8: people are shown by id; the Owner looks the id up on the Staff page."""
    output = "\n".join(cucumber_audit())

    for personal in ("jade", "mali", "@example.com"):
        assert personal not in output.lower()


def test_reading_writes_nothing(trail: dict[str, int]) -> None:
    mark = audit_mark()

    cucumber_audit()

    assert audit_mark() == mark


# ------------------------------------------------------------ filters
def test_by_person_id_or_email(trail: dict[str, int]) -> None:
    by_id = cucumber_audit("--person", str(trail["jade"]))
    by_email = cucumber_audit("--person", "JADE@example.com ")

    assert times(by_id) == ["2026-10-20 14:10", "2026-10-20 00:30", "2026-10-19 23:30"]
    assert by_email == by_id


def test_an_unknown_person_is_an_error(trail: dict[str, int]) -> None:
    with pytest.raises(CommandError, match="No account"):
        cucumber_audit("--person", "nobody@example.com")


def test_by_table_and_row(trail: dict[str, int]) -> None:
    lines = cucumber_audit("--table", "auth_user", "--row", str(trail["mali"]))

    assert times(lines) == ["2026-10-20 00:30", "2026-10-19 23:30"]


def test_dates_are_bangkok_days(trail: dict[str, int]) -> None:
    """00:30 on the 20th in Bangkok is still the 19th in UTC."""
    since = cucumber_audit("--since", "2026-10-20")
    until = cucumber_audit("--until", "2026-10-19")

    assert times(since) == ["2026-10-20 14:10", "2026-10-20 14:05", "2026-10-20 00:30"]
    assert times(until) == ["2026-10-19 23:30"]


def test_the_limit_shows_the_newest_and_the_total(trail: dict[str, int]) -> None:
    lines = cucumber_audit("--limit", "1")

    assert times(lines) == ["2026-10-20 14:10"]
    assert lines[-1] == "1 of 4 rows"


@pytest.mark.parametrize("option", ["--since", "--until"])
def test_a_date_that_isnt_one_is_an_error(trail: dict[str, int], option: str) -> None:
    with pytest.raises(CommandError):
        cucumber_audit(option, "20/10/2026")
