"""U0.9 AC1, AC8: what `references 0008_labels_and_seed` leaves (design §2.4).

Read from the migrated test database, as `test_reference_tables.py` reads the
U0.2a seeds. `0008` runs as System with `via = 'migration'`, so each change
it makes has its own audit row; the media codes keep their codes as labels
(Q1), so it writes none for them.
"""

import pytest

from cucumber.core.tests.rows import fetch_all
from cucumber.core.tests.trail import AuditRow, audit_rows_since, system_id

pytestmark = pytest.mark.django_db

STAGE_LABELS = {
    "S0": "Seed",
    "P0": "Sterilization / new species introduction",
    "P1": "Multiplication",
    "P2": "Growth",
    "A1": "Acclimatization (hardening off)",
    "P4": "Growth maturity (potted plants)",
    "P3": "Transport",
    "T1": "Digital content",
    "C0": "Clean",
}
CONTAINER_TYPES = {
    "flask_250ml": "250 ml flask",
    "magenta_box": "Magenta box",
    "pot_4in": "4-inch pot",
    "grow_bag": "Grow bag",
    "jar": "Jar",
    "disposable_cup": "Disposable cup",
    "tray": "Tray",
}
MEDIA_CODES = ["G001", "G002", "M001", "M002", "M003", "M004", "R001"]


def labels(table: str) -> dict[str, str]:
    """Each code's label in `table`."""
    rows = fetch_all(f"SELECT code, label FROM {table}")  # noqa: S608 (test names)
    return {str(code): str(label) for code, label in rows}


def migration_rows(table: str | None = None) -> list[AuditRow]:
    """Every audit row a migration wrote (`via = 'migration'`), oldest first."""
    return [row for row in audit_rows_since(0, table) if row.via == "migration"]


# ------------------------------------------------------------------- stages
def test_every_stage_has_its_ac1_label() -> None:
    assert labels("stages") == STAGE_LABELS


def test_s0_seed_is_active_with_no_subculture_days() -> None:
    rows = fetch_all(
        "SELECT code, sort_order, default_subculture_days, active FROM stages"
        " WHERE code = 'S0'"
    )

    assert rows == [("S0", 0, None, True)]


def test_s0_takes_order_0_and_no_other_stage_moves() -> None:
    """`P0` keeps 1, as SOP §3 shows (design §2.4)."""
    rows = fetch_all(
        "SELECT code, sort_order FROM stages WHERE active ORDER BY sort_order"
    )

    assert rows == [("S0", 0), ("P0", 1), ("P1", 2), ("P2", 3), ("A1", 4), ("P4", 5)]


def test_p3_t1_and_c0_stay_reserved() -> None:
    rows = fetch_all(
        "SELECT code, active, sort_order FROM stages"
        " WHERE code IN ('P3', 'T1', 'C0') ORDER BY code"
    )

    assert rows == [("C0", False, None), ("P3", False, None), ("T1", False, None)]


# -------------------------------------------------------------- media codes
def test_the_media_codes_are_still_labelled_with_their_codes() -> None:
    """Q1 (Owner, 2026-10-26): real labels come later, on the U0.10 list page."""
    rows = fetch_all("SELECT code, label, active FROM media_codes ORDER BY code")

    assert rows == [(code, code, True) for code in MEDIA_CODES]


# ---------------------------------------------------------- container types
def test_the_seven_container_types_are_there_and_active() -> None:
    rows = fetch_all("SELECT code, label, active FROM container_types")

    assert sorted(rows) == sorted(
        (code, label, True) for code, label in CONTAINER_TYPES.items()
    )


# -------------------------------------------------------------- the trail
def test_each_0008_change_has_one_audit_row() -> None:
    """1 insert for S0, 8 label updates, 7 container type inserts; no media."""
    found = [(row.table_name, row.row_pk, row.action) for row in migration_rows()]

    assert sorted(found) == sorted(
        [
            ("stages", "S0", "insert"),
            *(("stages", code, "update") for code in STAGE_LABELS if code != "S0"),
            *(("container_types", code, "insert") for code in CONTAINER_TYPES),
        ]
    )


def test_each_0008_row_is_by_system_via_migration_as_the_owner() -> None:
    rows = migration_rows()

    assert rows, "no audit row has via = 'migration'"
    assert {(row.actor_id, row.db_user, row.reason_code) for row in rows} == {
        (system_id(), "cucumber_owner", None)
    }


def test_each_stage_label_row_holds_the_code_before_and_the_label_after() -> None:
    rows = {
        row.row_pk: (row.before, row.after)
        for row in migration_rows("stages")
        if row.action == "update"
    }

    assert rows == {
        code: ({"label": code}, {"label": label})
        for code, label in STAGE_LABELS.items()
        if code != "S0"
    }


def test_the_s0_row_holds_the_whole_new_stage() -> None:
    inserted = [row for row in migration_rows("stages") if row.action == "insert"]

    assert [(row.before, row.after) for row in inserted] == [
        (
            None,
            {
                "code": "S0",
                "label": "Seed",
                "sort_order": 0,
                "default_subculture_days": None,
                "active": True,
            },
        )
    ]


def test_each_container_type_row_holds_the_whole_new_row() -> None:
    rows = {row.row_pk: row.after for row in migration_rows("container_types")}

    assert rows == {
        code: {"code": code, "label": label, "active": True}
        for code, label in CONTAINER_TYPES.items()
    }
