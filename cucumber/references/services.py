"""Rules for the references app. Views call these; they never hold rules themselves.

The Admin-only writers (U0.9 design §3.3). Each does the same steps, in this
order, and writes nothing before step 4:

1. `require(by, EDIT_REFERENCE_LISTS)`;
2. is the change allowed on this list (`list_fixed`, `stages_order_fixed`,
   `locations_fixed`);
3. the inputs, trimmed: the code's format, the label, a switch-off's reason;
4. `database_refusals()` and `audited()`;
5. inside: lock the row (or check the code is free), the rules that need the
   database, then save.

`require` and `audited` are imported by name, so a test can replace them and
see that order (AC20). A call that changes nothing saves nothing, so the audit
trigger writes no row, and the item comes back as it is.
"""

import re
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from django.contrib.auth.models import User

from cucumber.accounts.permissions import Permission, require
from cucumber.core.audit import Reason, audited, require_reason
from cucumber.core.refusals import database_refusals, refuse
from cucumber.ids.reading import ID_KINDS
from cucumber.references.lists import (
    LABEL_MAX_LENGTH,
    LIST_RULES,
    Change,
    ListName,
    ListRules,
)
from cucumber.references.models import Genus, ReasonList
from cucumber.references.reading import Item, label_column, manager, rows

# A code's rules after its format (design §3.1); only genera has one.
FURTHER_CODE_RULES: dict[str, Callable[[str], bool]] = {
    # A typed ID never reads as an SKU (U0.8 AC5a).
    "genera_code_not_id_prefix": lambda code: code not in ID_KINDS,
}


def add_item(
    by: User, name: ListName, code: str, label: str, *, via: str | None = None
) -> Item:
    """Add a media code, genus or container type (AC6)."""
    rules = allowed(by, name, Change.ADD)
    new_code = checked_code(rules, code)
    new_label = checked_label(name, label)
    with database_refusals(), audited(by, via=via):
        if manager(name).filter(code=new_code).exists():
            raise refuse(f"{name.value}_pkey")
        if name is ListName.GENERA:
            check_name_free(new_code, new_label)
        manager(name).create(code=new_code, **{label_column(name): new_label})
    return Item(new_code, new_label, True)


def edit_label(
    by: User, name: ListName, code: str, label: str, *, via: str | None = None
) -> Item:
    """Change an item's label; a genus's name (AC4, AC7)."""
    allowed(by, name, Change.LABEL)
    trimmed = code.strip()
    new_label = checked_label(name, label)
    with database_refusals(), audited(by, via=via):
        current = locked(name, trimmed)
        if current.label == new_label:
            return current
        if name is ListName.GENERA:
            check_name_free(current.code, new_label)
        save(name, current.code, {label_column(name): new_label})
    return replace(current, label=new_label)


def switch_off(
    by: User,
    name: ListName,
    code: str,
    reason: Reason | None,
    *,
    via: str | None = None,
) -> Item:
    """Switch an item off with an `archive` reason (AC10, AC11).

    The reason is asked even for an item already off, so the call always
    means the same thing (design §3.3).
    """
    allowed(by, name, Change.SWITCH_OFF)
    archive = require_reason(reason, ReasonList.ARCHIVE)
    return switched(by, name, code.strip(), active=False, via=via, reason=archive)


def switch_on(by: User, name: ListName, code: str, *, via: str | None = None) -> Item:
    """Switch an item back on; no reason asked (AC12)."""
    allowed(by, name, Change.SWITCH_ON)
    return switched(by, name, code.strip(), active=True, via=via, reason=None)


def switched(
    by: User,
    name: ListName,
    code: str,
    *,
    active: bool,
    via: str | None,
    reason: Reason | None,
) -> Item:
    """Steps 4 and 5 of a switch off or on."""
    with database_refusals(), audited(by, via=via, reason=reason):
        current = locked(name, code)
        if current.active == active:
            return current
        # A reserved stage has no place in the order (design §2.3).
        if active and name is ListName.STAGES and current.sort_order is None:
            raise refuse("stages_active_needs_sort_order")
        save(name, code, {"active": active})
    return replace(current, active=active)


# ----------------------------------------------------------------- the steps


def allowed(by: User, name: ListName, change: Change) -> ListRules:
    """Steps 1 and 2: the Admin, then a change this list takes."""
    require(by, Permission.EDIT_REFERENCE_LISTS)
    rules = LIST_RULES[name]
    if change not in rules.allowed:
        raise refuse(rules.refused_as)
    return rules


def checked_code(rules: ListRules, code: str) -> str:
    """Step 3: the code, trimmed, fits its list's rules, in order (AC6).

    Nothing is upper-cased for the person: `m001` is a format error.
    """
    trimmed = code.strip()
    format_rule, *further_rules = rules.code_rules
    if rules.code_pattern is None or not re.fullmatch(rules.code_pattern, trimmed):
        raise refuse(format_rule)
    for rule in further_rules:
        if not FURTHER_CODE_RULES[rule](trimmed):
            raise refuse(rule)
    return trimmed


def checked_label(name: ListName, label: str) -> str:
    """Step 3: the label, trimmed, is not blank and at most 100 characters."""
    trimmed = label.strip()
    if not trimmed or len(trimmed) > LABEL_MAX_LENGTH:
        raise refuse(label_rule(name))
    return trimmed


def label_rule(name: ListName) -> str:
    """The rule a bad label breaks (design §7)."""
    if name is ListName.GENERA:
        return "genera_name_valid"
    return f"{name.value}_label_valid"


def locked(name: ListName, code: str) -> Item:
    """Step 5: the item, its row locked; `list_item_unknown` if there is none."""
    row = rows(name).select_for_update(no_key=True).filter(code=code).first()
    if row is None:
        raise refuse("list_item_unknown")
    return Item(*row)


def check_name_free(code: str, new_name: str) -> None:
    """No other genus has this name (`genera_name_unique`)."""
    if Genus.objects.filter(name=new_name).exclude(code=code).exists():
        raise refuse("genera_name_unique")


def save(name: ListName, code: str, changes: dict[str, Any]) -> None:
    """One UPDATE of the changed column only, so the owner-only triggers and
    the audit row see just that change."""
    manager(name).filter(code=code).update(**changes)
