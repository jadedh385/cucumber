"""U0.9 design §2.1, §2.3, §12a: the list rules the database keeps itself.

AC3, AC11, AC14: `container_types` is protected like the other lists:
renaming and deleting a code is refused, and so is switching one off without
an `archive` reason, for the app user and the owner alike.

AC5, AC9: `stages_order_fixed` and `locations_fixed` keep the stage order and
the two locations for migrations: refused for `cucumber_app`, let through for
the owner (`cucumber_owner`, who runs migrations and this suite). A BEFORE
INSERT trigger fires even when `ON CONFLICT DO NOTHING` would skip the row
(review L4).

The new checks (`media_codes_code_format`, `container_types_code_format` and
the label rules) are refused by name in raw SQL, as the U0.2a schema tests do.
"""

import re

import psycopg
import pytest

from cucumber.core.tests.rows import (
    AppConnection,
    fetch_one,
    insert,
    refused_by,
    rule_name,
    run,
    update,
)
from cucumber.core.tests.stock import restore_reference_rows
from cucumber.core.tests.trail import as_system, system_id
from cucumber.references.lists import (
    CONTAINER_TYPE_PATTERN,
    LABEL_MAX_LENGTH,
    MEDIA_CODE_PATTERN,
    ListName,
)
from cucumber.references.tests.support import (
    ARCHIVE_REASON,
    LABEL_RULE,
    SEEDED,
    label_column,
    long_text,
)

pytestmark = pytest.mark.django_db

REASON = ARCHIVE_REASON.code


# ---------------------------------------------- as the app user (committing)
def as_app(
    app_db: AppConnection, statement: str, *, named: int, reason: str | None
) -> str:
    """Run `statement` as `cucumber_app`, someone named; how it ended.

    "saved", "no grant", or the rule that refused it.
    """
    try:
        with app_db.transaction():
            app_db.execute(
                b"SELECT set_config('cucumber.actor_id', %s, true)", [str(named)]
            )
            if reason is not None:
                app_db.execute(
                    b"SELECT set_config('cucumber.reason_code', %s, true)", [reason]
                )
            app_db.execute(statement.encode())
    except psycopg.errors.InsufficientPrivilege:
        return "no grant"
    except psycopg.Error as error:
        return rule_name(error) or str(error)
    return "saved"


# statement → (the reason set, how it must end). One committing test for all
# of them, in this order: each `app_db` test flushes the database afterwards.
APP_STATEMENTS: dict[str, tuple[str | None, str]] = {
    # AC3, AC14: container types are protected like the other lists.
    "UPDATE container_types SET code = 'magenta_crate' WHERE code = 'magenta_box'": (
        None,
        "container_types_code_rename",
    ),
    "DELETE FROM container_types WHERE code = 'magenta_box'": (None, "no grant"),
    # AC11: a switch-off needs a reason.
    "UPDATE container_types SET active = false WHERE code = 'magenta_box'": (
        None,
        "reason_required",
    ),
    # AC5: no new stage and no move in the order from the app.
    "INSERT INTO stages (code, label, sort_order, active)"
    " VALUES ('S9', 'S9', 99, true)": (None, "stages_order_fixed"),
    "UPDATE stages SET sort_order = 99 WHERE code = 'P2'": (
        None,
        "stages_order_fixed",
    ),
    # AC9: Lab and Nursery are fixed: no new location, none switched off.
    "INSERT INTO locations (code, label, active)"
    " VALUES ('greenhouse', 'Greenhouse', true)": (None, "locations_fixed"),
    # Review L4: the trigger fires before the conflict is looked at.
    "INSERT INTO locations (code, label, active) VALUES ('lab', 'Lab', true)"
    " ON CONFLICT DO NOTHING": (None, "locations_fixed"),
    "UPDATE locations SET active = false WHERE code = 'nursery'": (
        REASON,
        "locations_fixed",
    ),
    # What the writers do as the app still works (AC4, AC7, AC10, AC12).
    "UPDATE stages SET label = 'Growth' WHERE code = 'P2'": (None, "saved"),
    "UPDATE locations SET label = 'The Lab' WHERE code = 'lab'": (None, "saved"),
    "INSERT INTO container_types (code, label, active)"
    " VALUES ('jiffy_pot', 'Jiffy pot', true)": (None, "saved"),
    "UPDATE container_types SET label = 'Magenta box II' WHERE code = 'magenta_box'": (
        None,
        "saved",
    ),
    "UPDATE container_types SET active = false WHERE code = 'jiffy_pot'": (
        REASON,
        "saved",
    ),
    "UPDATE stages SET active = false WHERE code = 'P2'": (REASON, "saved"),
    # An ORM save writes every column: a guarded one set to itself is no change.
    "UPDATE stages SET sort_order = sort_order, label = 'Growth II'"
    " WHERE code = 'P2'": (None, "saved"),
    "UPDATE locations SET active = active, label = 'Lab' WHERE code = 'lab'": (
        None,
        "saved",
    ),
}


@pytest.mark.django_db(transaction=True)
def test_the_app_user_meets_each_list_rule_by_name(app_db: AppConnection) -> None:
    """AC3, AC5, AC9, AC11, AC14, as `cucumber_app` by raw SQL (design §12a).

    The flush before this test emptied the lists; System is back already.
    """
    restore_reference_rows()
    system = system_id()

    outcomes = {
        statement: as_app(app_db, statement, named=system, reason=reason)
        for statement, (reason, _) in APP_STATEMENTS.items()
    }

    assert outcomes == {
        statement: outcome for statement, (_, outcome) in APP_STATEMENTS.items()
    }


# -------------------------------------------------------- as the owner (AC3)
def test_the_owner_cant_rename_a_container_type() -> None:
    with refused_by("container_types_code_rename"), as_system():
        update("container_types", "magenta_box", {"code": "magenta_crate"}, "code")


def test_the_owner_cant_delete_a_container_type() -> None:
    with refused_by("container_types_no_delete"):
        run("DELETE FROM container_types WHERE code = 'magenta_box'")


def test_the_owner_cant_switch_a_container_type_off_without_a_reason() -> None:
    """AC11: the database asks again, whoever writes."""
    with refused_by("reason_required"), as_system():
        update("container_types", "magenta_box", {"active": False}, "code")


def test_the_owner_switches_a_container_type_off_with_a_reason() -> None:
    with as_system(ARCHIVE_REASON):
        update("container_types", "magenta_box", {"active": False}, "code")

    assert fetch_one(
        "SELECT active FROM container_types WHERE code = 'magenta_box'"
    ) == (False,)


# ------------------------------- the owner is let through (AC5, AC9, design §2.3)
def test_the_owner_may_add_a_stage() -> None:
    """A migration's path, with its own G0."""
    with as_system():
        insert(
            "stages",
            {"code": "S9", "label": "S9", "sort_order": 99, "active": True},
            returning="code",
        )

    assert fetch_one("SELECT sort_order FROM stages WHERE code = 'S9'") == (99,)


def test_the_owner_may_move_a_stage_in_the_order() -> None:
    with as_system():
        update("stages", "P4", {"sort_order": 99}, "code")

    assert fetch_one("SELECT sort_order FROM stages WHERE code = 'P4'") == (99,)


@pytest.mark.parametrize("on_conflict", ["", " ON CONFLICT DO NOTHING"])
def test_the_owner_may_add_a_location(on_conflict: str) -> None:
    with as_system():
        run(
            "INSERT INTO locations (code, label, active)"  # noqa: S608 (test text)
            f" VALUES ('greenhouse', 'Greenhouse', true){on_conflict}"
        )

    assert fetch_one("SELECT label FROM locations WHERE code = 'greenhouse'") == (
        "Greenhouse",
    )


def test_the_owner_may_switch_a_location_off_with_a_reason() -> None:
    with as_system(ARCHIVE_REASON):
        update("locations", "nursery", {"active": False}, "code")

    assert fetch_one("SELECT active FROM locations WHERE code = 'nursery'") == (False,)


# ------------------------------------------------- code formats (design §2.1)
# Not yet on the lists, so each can be added.
NEW_MEDIA_CODES = ["M01", "MS2", "ABCDEFGHIJ"]
BAD_MEDIA_CODES = [
    "m001",  # a small letter
    "M0",  # one too few
    "M0000000001",  # 11 characters
    "1M01",  # starts with a digit
    "M-01",
    "M 01",
    "M001\n",  # `$` before a newline (U0.8 G4 LOW)
    "",
]
NEW_CONTAINER_CODES = ["ab", "a" * 32, "pot_6in"]
BAD_CONTAINER_CODES = [
    "Magenta_Box",  # capitals (AC6)
    "m",  # one too few
    "a" * 33,  # one too many
    "4in_pot",  # starts with a digit
    "_box",
    "box-1",
    "magenta box",
    "jar\n",
]


def new_row(code: str) -> dict[str, object]:
    return {"code": code, "label": "A new one", "active": True}


def test_python_and_the_samples_agree() -> None:
    """Python's `re.fullmatch` gives the same split the database is tried on."""
    for good, bad, pattern in [
        (NEW_MEDIA_CODES, BAD_MEDIA_CODES, MEDIA_CODE_PATTERN),
        (NEW_CONTAINER_CODES, BAD_CONTAINER_CODES, CONTAINER_TYPE_PATTERN),
    ]:
        assert [code for code in good if not re.fullmatch(pattern, code)] == []
        assert [code for code in bad if re.fullmatch(pattern, code)] == []


@pytest.mark.parametrize("code", BAD_MEDIA_CODES)
def test_a_media_code_that_doesnt_fit_is_refused_by_name(code: str) -> None:
    with refused_by("media_codes_code_format"), as_system():
        insert("media_codes", new_row(code), returning="code")


@pytest.mark.parametrize("code", NEW_MEDIA_CODES)
def test_a_media_code_that_fits_is_accepted(code: str) -> None:
    with as_system():
        insert("media_codes", new_row(code), returning="code")

    assert fetch_one("SELECT count(*) FROM media_codes WHERE code = %s", [code]) == (1,)


def test_every_seeded_media_code_fits() -> None:
    """So 0006's pre-check has nothing to name on today's data (design §2.2)."""
    assert fetch_one(
        "SELECT count(*) FROM media_codes WHERE code !~ %s", [MEDIA_CODE_PATTERN]
    ) == (0,)


@pytest.mark.parametrize("code", BAD_CONTAINER_CODES)
def test_a_container_type_code_that_doesnt_fit_is_refused_by_name(code: str) -> None:
    with refused_by("container_types_code_format"), as_system():
        insert("container_types", new_row(code), returning="code")


@pytest.mark.parametrize("code", NEW_CONTAINER_CODES)
def test_a_container_type_code_that_fits_is_accepted(code: str) -> None:
    with as_system():
        insert("container_types", new_row(code), returning="code")

    assert fetch_one(
        "SELECT count(*) FROM container_types WHERE code = %s", [code]
    ) == (1,)


# ------------------------------------------------- label rules (design §2.1)
BAD_LABELS = {
    "blank": "",
    "spaces only": "   ",
    "a space before": " Growth",
    "a space after": "Growth ",
    "101 characters": long_text(LABEL_MAX_LENGTH + 1),
}


@pytest.mark.parametrize("name", list(SEEDED), ids=str)
@pytest.mark.parametrize("bad", sorted(BAD_LABELS))
def test_a_bad_label_is_refused_by_name(name: ListName, bad: str) -> None:
    """`<table>_label_valid`; on genera, `genera_name_valid`."""
    column = label_column(name)

    with refused_by(LABEL_RULE[name]), as_system():
        update(name.value, SEEDED[name], {column: BAD_LABELS[bad]}, "code")


@pytest.mark.parametrize("name", list(SEEDED), ids=str)
def test_a_label_of_100_characters_is_accepted(name: ListName) -> None:
    column = label_column(name)
    label = long_text(LABEL_MAX_LENGTH)

    with as_system():
        update(name.value, SEEDED[name], {column: label}, "code")

    assert fetch_one(
        f"SELECT {column} FROM {name.value} WHERE code = %s",  # noqa: S608 (test names)
        [SEEDED[name]],
    ) == (label,)


@pytest.mark.parametrize(
    ("table", "taken"),
    [("media_codes", "M001"), ("genera", "HYA"), ("container_types", "magenta_box")],
)
def test_a_code_taken_is_refused_by_the_primary_key_s_name(
    table: str, taken: str
) -> None:
    """The name `database_refusals` turns into the service's own refusal when
    two Admins add the same code at once (design §3.3)."""
    column = "name" if table == "genera" else "label"

    with refused_by(f"{table}_pkey"), as_system():
        insert(table, {"code": taken, column: "Again", "active": True}, "code")


def test_a_new_container_type_with_a_blank_label_is_refused_by_name() -> None:
    with refused_by("container_types_label_valid"), as_system():
        insert(
            "container_types",
            {"code": "jiffy_pot", "label": "", "active": True},
            returning="code",
        )
