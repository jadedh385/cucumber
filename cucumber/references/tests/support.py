"""Set-up shared by the U0.9 service tests (design §12a).

The seed rows each list is tried on, a way to switch one off without the
writers (so a reader or writer test starts from a known state), and a check
that a refused change left no trace (AC21).
"""

from collections.abc import Iterator
from contextlib import contextmanager

from cucumber.core.audit import Reason
from cucumber.core.tests.rows import as_system, fetch_all, update
from cucumber.core.tests.trail import NO_LONGER_USED, audit_mark, audit_rows_since
from cucumber.references.lists import EDITABLE_TABLES, ListName

ARCHIVE_REASON = Reason(NO_LONGER_USED)

# One seeded code per list the Admin edits (the migrations' own seeds).
SEEDED: dict[ListName, str] = {
    ListName.STAGES: "P1",
    ListName.MEDIA_CODES: "M001",
    ListName.LOCATIONS: "lab",
    ListName.GENERA: "HYA",
    ListName.CONTAINER_TYPES: "magenta_box",
}

# The label column is `name` on genera only.
LABEL_COLUMN = {ListName.GENERA: "name"}

# The rule a bad label is refused by, per list (design §7).
LABEL_RULE = {
    ListName.STAGES: "stages_label_valid",
    ListName.MEDIA_CODES: "media_codes_label_valid",
    ListName.LOCATIONS: "locations_label_valid",
    ListName.GENERA: "genera_name_valid",
    ListName.CONTAINER_TYPES: "container_types_label_valid",
}

# The lists that take a new code (design §3.1), with a code that fits each.
ADDABLE: dict[ListName, str] = {
    ListName.MEDIA_CODES: "M777",
    ListName.GENERA: "XYZ",
    ListName.CONTAINER_TYPES: "jiffy_pot",
}

# Lists whose items go off and on (stages, media, genera, container types).
SWITCHABLE = [
    ListName.STAGES,
    ListName.MEDIA_CODES,
    ListName.GENERA,
    ListName.CONTAINER_TYPES,
]

# The fixed lists, with a value from each.
FIXED: dict[ListName, str] = {ListName.ACTIONS: "intake", ListName.COUNT_UNITS: "plant"}


def label_column(name: ListName) -> str:
    return LABEL_COLUMN.get(name, "label")


def switched_off(name: ListName, code: str) -> None:
    """Switch an item off in set-up, as System with an `archive` reason."""
    with as_system(ARCHIVE_REASON):
        update(name.value, code, {"active": False}, "code")


def long_text(length: int) -> str:
    return "x" * length


def table_rows(name: ListName) -> list[tuple[object, ...]]:
    """The list's table as it is; a fixed list has none (it is in code)."""
    if name.value not in EDITABLE_TABLES:
        return []
    return fetch_all(f"SELECT * FROM {name.value} ORDER BY 1")  # noqa: S608


@contextmanager
def nothing_written(name: ListName) -> Iterator[None]:
    """Inside, a change was refused: the list is as it was and no audit row
    was written for anything (AC21)."""
    mark = audit_mark()
    rows = table_rows(name)
    yield
    assert table_rows(name) == rows, f"{name.value} changed"
    assert audit_rows_since(mark) == [], "an audit row was written"
