"""U0.2a: the tables have the agreed shape and every rule has its stable name.

Spec story S3 (one agreed schema), design §2 (tables) and §7.1 (names). The
column lists are exact on purpose: `qty_contaminated` (Q4), `week` and any
availability column (SOP §2 principle 6) must never appear.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

from cucumber.core.tests.rows import fetch_all, fetch_one
from cucumber.core.tests.schema_spec import (
    CONSTRAINT_NAMES,
    NULLABLE_COLUMNS,
    PRIMARY_KEYS,
    TABLE_COLUMNS,
    TRIGGER_NAMES,
    TWO_COLUMN_LINKS,
)

pytestmark = pytest.mark.django_db

DESIGN_NOTE = Path(settings.BASE_DIR) / "docs/roadmap/units/u0.2-design.md"


def columns_of(table: str) -> set[str]:
    rows = fetch_all(
        "SELECT column_name FROM information_schema.columns"
        " WHERE table_schema = 'public' AND table_name = %s",
        [table],
    )
    return {str(row[0]) for row in rows}


@pytest.mark.parametrize("table", sorted(TABLE_COLUMNS))
def test_table_has_exactly_the_design_columns(table: str) -> None:
    assert columns_of(table) == TABLE_COLUMNS[table]


@pytest.mark.parametrize("table", sorted(PRIMARY_KEYS))
def test_primary_key_is_the_design_key(table: str) -> None:
    rows = fetch_all(
        "SELECT a.attname FROM pg_index i"
        " JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)"
        " WHERE i.indrelid = to_regclass(%s) AND i.indisprimary",
        [f"public.{table}"],
    )
    assert [row[0] for row in rows] == PRIMARY_KEYS[table]


@pytest.mark.parametrize("table", sorted(TABLE_COLUMNS))
def test_only_the_design_null_columns_are_nullable(table: str) -> None:
    """A CHECK lets NULL through, so NOT NULL is what makes the rules bite."""
    rows = fetch_all(
        "SELECT column_name FROM information_schema.columns"
        " WHERE table_schema = 'public' AND table_name = %s"
        " AND is_nullable = 'YES' AND is_generated = 'NEVER'",
        [table],
    )
    assert {str(row[0]) for row in rows} == NULLABLE_COLUMNS.get(table, set())


@pytest.mark.parametrize("name", TWO_COLUMN_LINKS)
def test_two_column_links_are_checked_at_once(name: str) -> None:
    """Not deferred to commit, so a bad link fails on its own statement (M3)."""
    row = fetch_one(
        "SELECT contype, condeferrable FROM pg_constraint"
        " WHERE conname = %s AND connamespace = 'public'::regnamespace",
        [name],
    )
    assert row == ("f", False)


def test_plant_name_key_is_worked_out_by_the_database() -> None:
    """Q6: `name_key` is a stored generated column, never typed."""
    rows = fetch_all(
        "SELECT is_generated FROM information_schema.columns"
        " WHERE table_name = 'plants' AND column_name = 'name_key'"
    )
    assert rows == [("ALWAYS",)]


def test_no_table_stores_availability() -> None:
    """SOP §2 principle 6 and Q4: no availability, contamination or week column."""
    rows = fetch_all(
        "SELECT table_name, column_name FROM information_schema.columns"
        " WHERE table_schema = 'public'"
        " AND (column_name LIKE '%%availab%%' OR column_name IN"
        " ('qty_contaminated', 'week'))"
    )
    assert rows == []


def existing_rule_names() -> set[str]:
    rows = fetch_all(
        "SELECT conname FROM pg_constraint"
        " WHERE connamespace = 'public'::regnamespace"
        " UNION SELECT indexrelid::regclass::text FROM pg_index"
        " UNION SELECT tgname FROM pg_trigger WHERE NOT tgisinternal"
    )
    return {str(row[0]) for row in rows}


def test_every_named_rule_exists() -> None:
    """Design §7.1: the service maps a refusal to a message by its name."""
    missing = sorted(set(CONSTRAINT_NAMES) - existing_rule_names())
    assert missing == []


def test_every_protection_trigger_exists() -> None:
    """Design §4: append-only, no-delete, no-rename and static-SKU triggers."""
    missing = sorted(set(TRIGGER_NAMES) - existing_rule_names())
    assert missing == []


# ------------------------------------------------------------------- AC1


def rule_table_rows() -> dict[int, list[str]]:
    """The rows of design §5, by SOP §5 rule number: DB, Svc, Why not."""
    text = DESIGN_NOTE.read_text(encoding="utf-8")
    section = text.split("## 5. Rule-to-enforcement table", 1)[1]
    section = section.split("\n## ", 1)[0]
    rows: dict[int, list[str]] = {}
    for line in section.splitlines():
        match = re.match(r"\|\s*(\d+)\s", line)
        if match:
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            rows[int(match.group(1))] = cells[1:]
    return rows


def test_ac1_every_sop_rule_has_an_enforcement_row() -> None:
    rows = rule_table_rows()
    assert sorted(rows) == list(range(1, 14))
    unexplained = [number for number, cells in rows.items() if set(cells) <= {"", "—"}]
    assert unexplained == []
