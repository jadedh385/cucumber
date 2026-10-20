"""U0.2a: reference lists and their seed data (design §2.1; AC20, AC21).

Renaming and deleting codes is covered for every list in
core/tests/test_protection.py; here are the per-list checks and the seeds.
"""

import pytest

from cucumber.core.audit import Reason
from cucumber.core.tests.rows import (
    as_int,
    fetch_all,
    fetch_one,
    insert,
    make_batch,
    refused_by,
    run,
    update,
)
from cucumber.core.tests.trail import as_system

pytestmark = pytest.mark.django_db


def codes(sql: str) -> list[str]:
    return [str(row[0]) for row in fetch_all(sql)]


# ------------------------------------------------------------------- seeds


def test_active_stages_run_p0_p1_p2_a1_p4() -> None:
    """AC21 and D-06: A1 sits between P2 and P4."""
    active = codes("SELECT code FROM stages WHERE active ORDER BY sort_order")
    assert active == ["P0", "P1", "P2", "A1", "P4"]


def test_reserved_stages_are_inactive_with_no_sort_order() -> None:
    rows = fetch_all(
        "SELECT code, active, sort_order FROM stages"
        " WHERE code IN ('P3', 'T1', 'C0') ORDER BY code"
    )
    assert rows == [("C0", False, None), ("P3", False, None), ("T1", False, None)]


def test_subculture_intervals_are_left_blank_until_u2_2() -> None:
    sql = "SELECT code FROM stages WHERE default_subculture_days IS NOT NULL"
    assert codes(sql) == []


def test_locations_are_lab_and_nursery() -> None:
    """D-14: two locations."""
    rows = fetch_all("SELECT code, label, active FROM locations ORDER BY code")
    assert rows == [("lab", "Lab", True), ("nursery", "Nursery", True)]


def test_media_codes_are_seeded() -> None:
    active = codes("SELECT code FROM media_codes WHERE active ORDER BY code")
    assert active == ["G001", "G002", "M001", "M002", "M003", "M004", "R001"]


def test_genera_are_seeded() -> None:
    rows = fetch_all("SELECT code, name FROM genera WHERE active ORDER BY code")
    assert rows == [("ALC", "Alocasia"), ("HYA", "Hoya"), ("PHL", "Philodendron")]


SEEDED_REASONS = {
    "void": ["duplicate entry", "wrong batch", "wrong plant", "test entry", "other"],
    "correction": [
        "wrong quantity", "wrong media code", "wrong stage", "wrong date", "other",
    ],
    "loss": [
        "failed acclimatization", "pest", "rot", "damage", "unknown", "other",
    ],
}  # fmt: skip


@pytest.mark.parametrize("applies_to", sorted(SEEDED_REASONS))
def test_reasons_are_seeded_per_list(applies_to: str) -> None:
    rows = fetch_all(
        "SELECT lower(label) FROM reasons WHERE applies_to = %s AND active",
        [applies_to],
    )
    assert sorted(str(row[0]) for row in rows) == sorted(SEEDED_REASONS[applies_to])


# ------------------------------------------------------------------ stages


def new_stage(code: str, sort_order: int | None) -> dict[str, object]:
    return {
        "code": code,
        "label": code,
        "sort_order": sort_order,
        "default_subculture_days": None,
        "active": True,
    }


def test_two_stages_cannot_share_a_sort_order() -> None:
    """AC21."""
    taken = as_int(fetch_one("SELECT sort_order FROM stages WHERE code = 'P2'")[0])
    with refused_by("stages_sort_order_unique"):
        insert("stages", new_stage("X1", taken), returning="code")


def test_an_active_stage_needs_a_sort_order() -> None:
    with refused_by("stages_active_needs_sort_order"):
        update("stages", "P3", {"active": True}, key_column="code")


def test_subculture_interval_must_be_positive() -> None:
    with refused_by("stages_subculture_days_positive"):
        update("stages", "P0", {"default_subculture_days": 0}, key_column="code")


def test_a_used_stage_can_be_deactivated(plant: int, user: int) -> None:
    """AC20: deactivating is how a code is retired."""
    make_batch(plant, user, location_code="lab", stage_code="P2")
    with as_system(Reason("archive_no_longer_used")):
        update("stages", "P2", {"active": False}, key_column="code")
    assert fetch_one("SELECT active FROM stages WHERE code = 'P2'") == (False,)


def test_a_used_stage_cannot_be_deleted(plant: int, user: int) -> None:
    """AC20: refused by the trigger even before the foreign key is checked."""
    make_batch(plant, user, location_code="lab", stage_code="P2")
    with refused_by("stages_no_delete"):
        run("DELETE FROM stages WHERE code = 'P2'")


def test_a_used_stage_cannot_be_renamed(plant: int, user: int) -> None:
    """AC20."""
    make_batch(plant, user, location_code="lab", stage_code="P2")
    with refused_by("stages_code_rename"):
        update("stages", "P2", {"code": "P2b"}, key_column="code")


# ------------------------------------------------------- genera and reasons


def new_genus(code: str, name: str) -> dict[str, object]:
    return {"code": code, "name": name, "active": True}


@pytest.mark.parametrize("code", ["PH", "phl", "PH1"])
def test_genus_code_is_three_capital_letters(code: str) -> None:
    with refused_by("genera_code_format"):
        insert("genera", new_genus(code, f"Genus {code}"), returning="code")


def test_two_genera_cannot_share_a_name() -> None:
    with refused_by("genera_name_unique"):
        insert("genera", new_genus("PHX", "Philodendron"), returning="code")


def test_the_admin_can_add_a_genus() -> None:
    with as_system():
        insert("genera", new_genus("ANT", "Anthurium"), returning="code")
    assert fetch_one("SELECT name FROM genera WHERE code = 'ANT'") == ("Anthurium",)


def test_a_reason_belongs_to_a_known_list() -> None:
    reason = {"code": "odd", "label": "Odd", "applies_to": "count", "active": True}
    with refused_by("reasons_applies_to_valid"):
        insert("reasons", reason, returning="code")
