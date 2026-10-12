"""The agreed U0.2a schema as data, for the schema tests (design §2, §4, §7.1)."""

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

# Columns the design marks "null" (§2); every other column is NOT NULL. A CHECK
# treats NULL as passing, so a nullable `status` or `qty_in` would slip past
# every rule above it.
NULLABLE_COLUMNS = {
    "stages": {"sort_order", "default_subculture_days"},
    "plants": {"sku", "source", "source_note", "vendor_id", "zoho_ref",
               "min_saleable_qty"},
    "plant_status_changes": {"sku_assigned", "reason"},
    "batches": {"parent_batch_id", "stage_code", "closed_at", "voided_at"},
    "events": {"counted_qty", "media_code", "stage_to", "reason_code",
               "voids_event_id", "corrects_event_id"},
    "audit_log": {"before", "after", "reason"},
}  # fmt: skip

# The links Django can't declare (design §2.4, M3). They are checked at once,
# not at commit, so a bad link fails on its own statement.
TWO_COLUMN_LINKS = [
    "batch_parent_same_plant", "event_void_same_batch",
    "event_correction_same_batch", "plant_sku_belongs_to_plant",
]  # fmt: skip
