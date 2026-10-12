"""U0.2a: the tables have the agreed shape and every rule has its stable name.

Spec story S3 (one agreed schema), design §2 (tables) and §7.1 (names). The
column lists are exact on purpose: `qty_contaminated` (Q4), `week` and any
availability column (SOP §2 principle 6) must never appear.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings

from cucumber.core.tests.rows import fetch_all

pytestmark = pytest.mark.django_db

TABLE_COLUMNS = {
    "genera": {"code", "name", "active"},
    "stages": {"code", "label", "sort_order", "default_subculture_days", "active"},
    "media_codes": {"code", "label", "active"},
    "locations": {"code", "label", "active"},
    "reasons": {"code", "label", "applies_to", "active"},
    "vendors": {"zoho_contact_id", "name", "active", "synced_at"},
    "plants": {
        "id", "genus_code", "full_name", "name_key", "sku", "status", "source",
        "source_note", "vendor_id", "zoho_ref", "min_saleable_qty", "notes",
        "created_at", "created_by",
    },
    "skus": {"sku", "plant_id", "genus_code", "assigned_at", "assigned_by"},
    "plant_status_changes": {
        "id", "plant_id", "from_status", "to_status", "sku_assigned",
        "changed_by", "changed_at", "reason",
    },
    "batches": {
        "id", "plant_id", "plant_seq", "parent_batch_id", "origin",
        "created_operation_id", "location_code", "stage_code", "quarantined",
        "status", "live_count", "created_at", "created_by", "closed_at",
        "voided_at",
    },
    "operations": {"id", "recorded_by", "recorded_at"},
    "events": {
        "id", "operation_id", "batch_id", "action", "qty_in", "qty_out",
        "counted_qty", "media_code", "stage_to", "staff_id", "recorded_by",
        "occurred_at", "recorded_at", "reason_code", "voids_event_id",
        "corrects_event_id", "note", "entered_via",
    },
    "event_reviews": {"id", "event_id", "reviewer_id", "reviewed_at", "note"},
    "audit_log": {
        "id", "actor_id", "at", "table_name", "row_pk", "action", "before",
        "after", "reason",
    },
}  # fmt: skip

PRIMARY_KEYS = {
    "genera": ["code"],
    "stages": ["code"],
    "media_codes": ["code"],
    "locations": ["code"],
    "reasons": ["code"],
    "vendors": ["zoho_contact_id"],
    "skus": ["sku"],
    "operations": ["id"],
} | {
    table: ["id"]
    for table in [
        "plants", "plant_status_changes", "batches", "events", "event_reviews",
        "audit_log",
    ]
}  # fmt: skip

# Every concrete name in design §7.1. Checks, unique indexes and foreign keys
# are found in the catalogue; triggers by their trigger name.
CONSTRAINT_NAMES = [
    "plant_status_valid", "plant_portfolio_needs_sku", "plant_sku_format",
    "plant_sku_matches_genus", "plant_sku_unique", "plant_sku_belongs_to_plant",
    "plant_source_valid", "plant_source_required",
    "plant_portfolio_needs_zoho_link", "plant_vendor_only_if_purchased",
    "plant_min_saleable_positive", "plant_name_valid",
    "plant_name_unique_in_genus",
    "batch_origin_valid", "batch_status_valid", "batch_needs_parent",
    "batch_not_own_parent", "batch_lab_needs_stage", "batch_count_not_negative",
    "batch_closed_needs_zero", "batch_closed_at_matches",
    "batch_voided_at_matches", "batch_quarantine_origin",
    "batch_plant_seq_unique", "batch_parent_same_plant",
    "event_action_valid", "event_entered_via_valid", "event_qty_not_negative",
    "event_qty_one_direction", "event_counted_not_negative",
    "event_void_target", "event_correction_target", "event_reason_required",
    "event_not_in_future", "event_within_7_days", "event_void_once",
    "event_void_same_batch", "event_correction_same_batch",
    "event_review_once", "operations_pkey",
    "skus_pkey", "skus_prefix_matches_genus", "skus_sku_plant_unique",
    "genera_code_format", "genera_name_unique", "stages_sort_order_unique",
    "stages_active_needs_sort_order", "stages_subculture_days_positive",
    "reasons_applies_to_valid",
] + [
    f"event_{action}_shape"
    for action in [
        "intake", "subculture", "stage_change", "count", "contamination",
        "split", "quarantine", "release", "transfer", "out", "loss", "close",
        "void",
    ]
]  # fmt: skip

INSERT_ONLY_TABLES = [
    "events", "operations", "event_reviews", "plant_status_changes", "skus",
    "audit_log",
]  # fmt: skip
REFERENCE_TABLES = ["genera", "stages", "media_codes", "locations", "reasons"]
NO_DELETE_TABLES = ["plants", "batches", "vendors", *REFERENCE_TABLES]

TRIGGER_NAMES = (
    ["plant_sku_static", "events_recorded_at_now"]
    + [f"{table}_append_only" for table in INSERT_ONLY_TABLES]
    + [f"{table}_no_delete" for table in NO_DELETE_TABLES]
    + [f"{table}_code_rename" for table in REFERENCE_TABLES]
)

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
