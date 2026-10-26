"""What each reference list allows (U0.9 design §3.1). No database.

The patterns are the database checks' regexes (`^…$`); Python checks them
with `re.fullmatch`, so a trailing newline can't pass (U0.8 G4 LOW).
"""

from dataclasses import dataclass
from enum import StrEnum

MEDIA_CODE_PATTERN = r"^[A-Z][A-Z0-9]{2,9}$"  # M001, G002, R001
GENUS_CODE_PATTERN = r"^[A-Z]{3}$"  # PHL
CONTAINER_TYPE_PATTERN = r"^[a-z][a-z0-9_]{1,31}$"  # magenta_box
LABEL_MAX_LENGTH = 100


class ListName(StrEnum):
    STAGES = "stages"
    MEDIA_CODES = "media_codes"
    LOCATIONS = "locations"
    GENERA = "genera"
    CONTAINER_TYPES = "container_types"
    ACTIONS = "actions"  # fixed (design §4)
    COUNT_UNITS = "count_units"  # fixed (design §4)


class Change(StrEnum):
    ADD = "add"
    LABEL = "label"
    SWITCH_OFF = "switch_off"
    SWITCH_ON = "switch_on"


@dataclass(frozen=True)
class ListRules:
    name: ListName
    allowed: frozenset[Change]
    refused_as: str  # the rule for a change not allowed
    code_pattern: str | None  # None: no codes added
    code_rules: tuple[str, ...]  # checked in order; genera has two
    order: str  # "sort_order", "code", "label" or "fixed"


ALL_CHANGES = frozenset(Change)
SWITCHING = frozenset({Change.LABEL, Change.SWITCH_OFF, Change.SWITCH_ON})
LABEL_ONLY = frozenset({Change.LABEL})
NO_CHANGES: frozenset[Change] = frozenset()

LIST_RULES: dict[ListName, ListRules] = {
    rules.name: rules
    for rules in (
        ListRules(
            ListName.STAGES, SWITCHING, "stages_order_fixed", None, (), "sort_order"
        ),
        ListRules(ListName.LOCATIONS, LABEL_ONLY, "locations_fixed", None, (), "code"),
        ListRules(
            ListName.MEDIA_CODES,
            ALL_CHANGES,
            "",
            MEDIA_CODE_PATTERN,
            ("media_codes_code_format",),
            "code",
        ),
        ListRules(
            ListName.GENERA,
            ALL_CHANGES,
            "",
            GENUS_CODE_PATTERN,
            ("genera_code_format", "genera_code_not_id_prefix"),
            "code",
        ),
        ListRules(
            ListName.CONTAINER_TYPES,
            ALL_CHANGES,
            "",
            CONTAINER_TYPE_PATTERN,
            ("container_types_code_format",),
            "label",
        ),
        ListRules(ListName.ACTIONS, NO_CHANGES, "list_fixed", None, (), "fixed"),
        ListRules(ListName.COUNT_UNITS, NO_CHANGES, "list_fixed", None, (), "fixed"),
    )
}

# The tables the Admin edits. `reasons` isn't one (U0.9 spec Q7).
EDITABLE_TABLES = tuple(
    rules.name.value for rules in LIST_RULES.values() if rules.allowed
)
