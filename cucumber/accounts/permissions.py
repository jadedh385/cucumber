"""The permission matrix: who may do what (U0.6 design §2, AC3).

One module holds every "who may do what". Pages, services, templates and the
generated tests all read it; nothing else decides. Each row lists its roles
in full, so a row reads the same as the spec's table.

A "✅ except" cell stays ✅ here: the exception is a rule in the service
(`narrowed_by` names it), because it depends on the event, not only on the
role.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar

from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import PermissionDenied

from cucumber.core.refusals import message_for

View = TypeVar("View", bound=Callable[..., Any])


class Role(StrEnum):
    """The four roles, by their group names (U0.2 design §2.7)."""

    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    TECH = "tech"
    READ_ONLY = "read_only"


class Permission(StrEnum):
    """One per matrix row."""

    LOG_WORK = "log_work"
    SPLIT_CLOSE_LOSS = "split_close_loss"
    RELEASE_QUARANTINE = "release_quarantine"
    UNDO_OWN = "undo_own"
    REVIEW_EVENTS = "review_events"
    VOID_OR_CORRECT = "void_or_correct"
    REVIEW_VOIDS = "review_voids"
    ENTER_FOR_OTHERS = "enter_for_others"
    PLANT_LIFECYCLE = "plant_lifecycle"
    RECLASSIFY_GENUS = "reclassify_genus"
    ZOHO_LINK = "zoho_link"
    EDIT_REFERENCE_LISTS = "edit_reference_lists"
    SEE_ZOHO_REFS = "see_zoho_refs"
    VIEW_DASHBOARDS = "view_dashboards"
    MANAGE_USERS = "manage_users"
    OWN_ACCOUNT = "own_account"


class Built(StrEnum):
    """Where a row is checked today; LATER rows have no page or service yet."""

    PAGES = "pages"
    SERVICES = "services"
    BOTH = "both"
    LATER = "later"


@dataclass(frozen=True)
class Row:
    """One row of the matrix. `None` in `allowed` is an account with no role."""

    permission: Permission
    label: str
    allowed: frozenset[Role | None]
    narrowed_by: str = ""
    refused_as: str = "role_not_allowed"
    built: Built = Built.LATER


EVERY_ROLE: frozenset[Role | None] = frozenset(Role)
WORKERS: frozenset[Role | None] = frozenset({Role.ADMIN, Role.SUPERVISOR, Role.TECH})
REVIEWERS: frozenset[Role | None] = frozenset({Role.ADMIN, Role.SUPERVISOR})
ADMIN_ONLY: frozenset[Role | None] = frozenset({Role.ADMIN})

MATRIX: tuple[Row, ...] = (
    Row(
        Permission.LOG_WORK,
        "Register plant, create batch, log events",
        WORKERS,
        narrowed_by="staff_must_be_you",
        built=Built.SERVICES,
    ),
    Row(
        Permission.SPLIT_CLOSE_LOSS,
        "Split, close, record loss, quarantine",
        WORKERS,
        narrowed_by="staff_must_be_you",
        built=Built.SERVICES,
    ),
    Row(
        Permission.RELEASE_QUARANTINE,
        "Release a batch from quarantine",
        WORKERS,
        narrowed_by="staff_must_be_you",
        built=Built.SERVICES,
    ),
    Row(
        Permission.UNDO_OWN,
        "Undo an entry they saved, within 10 minutes",
        WORKERS,
        narrowed_by="undo_not_yours, undo_too_late",
        built=Built.SERVICES,
    ),
    Row(
        Permission.REVIEW_EVENTS,
        "Review events",
        REVIEWERS,
        narrowed_by="review_not_allowed",
        built=Built.SERVICES,
    ),
    Row(
        Permission.VOID_OR_CORRECT,
        "Void or correct an event",
        REVIEWERS,
        narrowed_by="fix_own_entry",
        built=Built.SERVICES,
    ),
    Row(
        Permission.REVIEW_VOIDS,
        "Review Voids (including Undo)",
        ADMIN_ONLY,
        built=Built.SERVICES,
    ),
    Row(
        Permission.ENTER_FOR_OTHERS,
        "Enter work done by another staff member",
        REVIEWERS,
        refused_as="staff_must_be_you",
        built=Built.SERVICES,
    ),
    Row(
        Permission.PLANT_LIFECYCLE,
        "Promote / demote / retire / void a plant, assign SKU",
        ADMIN_ONLY,
        built=Built.SERVICES,
    ),
    Row(
        Permission.RECLASSIFY_GENUS,
        "Reclassify a plant's genus (new SKU)",
        ADMIN_ONLY,
        built=Built.SERVICES,
    ),
    Row(
        Permission.ZOHO_LINK,
        "Complete the Zoho link (vendor, zoho_ref)",
        ADMIN_ONLY,
    ),
    Row(Permission.EDIT_REFERENCE_LISTS, "Edit reference lists", ADMIN_ONLY),
    Row(Permission.SEE_ZOHO_REFS, "See Zoho references", ADMIN_ONLY),
    Row(Permission.VIEW_DASHBOARDS, "View dashboards", EVERY_ROLE),
    Row(
        Permission.MANAGE_USERS,
        "Manage users and give roles",
        ADMIN_ONLY,
        built=Built.BOTH,
    ),
    Row(
        Permission.OWN_ACCOUNT,
        "Home, log in, log out, change own password",
        EVERY_ROLE | {None},
        built=Built.PAGES,
    ),
)


@dataclass(frozen=True)
class Standing:
    """A person as the checks see them, read from the database now (§4.1)."""

    user_id: int | None
    is_active: bool
    role: Role | None


class NotAllowed(PermissionDenied):
    """Refused by role or account state: always a 403, never a page message.

    A `PermissionDenied`, not a `Refused`, so a view's `except Refused` can't
    catch it (§4.1). Carries `rule` and `message` like a refusal.
    """

    def __init__(self, rule: str) -> None:
        self.rule = rule
        self.message = message_for(rule)
        super().__init__(self.message)


def row_of(permission: Permission) -> Row:
    """The matrix row for `permission`."""
    raise NotImplementedError("U0.6 G3")


def may(role: Role | None, permission: Permission) -> bool:
    """True when the matrix allows `role` the row's action."""
    raise NotImplementedError("U0.6 G3")


def standing(user: User | AnonymousUser) -> Standing:
    """Active flag and role, read from the database now (one query)."""
    raise NotImplementedError("U0.6 G3")


def require(user: User | AnonymousUser, permission: Permission) -> Standing:
    """The person's standing, or `NotAllowed`: account_not_active / role_not_allowed."""
    raise NotImplementedError("U0.6 G3")


def allowed_for(permission: Permission) -> Callable[[View], View]:
    """Label a view with its matrix row (`view.cucumber_permission`, §3.1)."""
    raise NotImplementedError("U0.6 G3")
