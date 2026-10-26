"""Rules for the references app. Views call these; they never hold rules themselves.

The Admin-only writers (U0.9 design §3.3): permission check, then `audited()`.
"""

from django.contrib.auth.models import User

from cucumber.core.audit import Reason
from cucumber.references.lists import ListName
from cucumber.references.reading import Item

NOT_BUILT = "U0.9 G3"


def add_item(
    by: User, name: ListName, code: str, label: str, *, via: str | None = None
) -> Item:
    """Add a media code, genus or container type (AC6)."""
    raise NotImplementedError(NOT_BUILT)


def edit_label(
    by: User, name: ListName, code: str, label: str, *, via: str | None = None
) -> Item:
    """Change an item's label; a genus's name (AC4, AC7)."""
    raise NotImplementedError(NOT_BUILT)


def switch_off(
    by: User,
    name: ListName,
    code: str,
    reason: Reason | None,
    *,
    via: str | None = None,
) -> Item:
    """Switch an item off with an `archive` reason (AC10, AC11)."""
    raise NotImplementedError(NOT_BUILT)


def switch_on(by: User, name: ListName, code: str, *, via: str | None = None) -> Item:
    """Switch an item back on; no reason asked (AC12)."""
    raise NotImplementedError(NOT_BUILT)
