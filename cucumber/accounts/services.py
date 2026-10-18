"""Rules for the accounts app. Views call these; they never hold rules themselves.

A role is a Django group (U0.2 design §2.7); the permission matrix is U0.6.
Logging in, the wrong-password lock and the Staff pages are U0.5 (design §7).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.contrib.auth.models import User
from django.http import HttpRequest

ADMIN = "admin"
SUPERVISOR = "supervisor"
TECH = "tech"

NOT_BUILT = "U0.5 G3"

# Design §4, §7.2: rules, not settings, so the tests read them from here.
SESSION_MAX_AGE = timedelta(days=30)
LOCK_AFTER_FAILURES = 5
LOCK_WINDOW = timedelta(minutes=15)
ADDRESS_LIMIT = 50


@dataclass(frozen=True)
class NewAccount:
    """An account just added, and its temporary password (shown once, §6.2)."""

    account: User
    password: str


def has_role(user: User, role: str) -> bool:
    """True when `user` is in the role's group."""
    return user.groups.filter(name=role).exists()


def members_of(role: str) -> frozenset[int]:
    """The ids of every user in the role's group."""
    return frozenset(
        User.objects.filter(groups__name=role).values_list("id", flat=True)
    )


# ------------------------------------------------------------------ accounts


def email_key(text: str) -> str:
    """The email as stored and compared: trimmed and lowercase (§2.1)."""
    raise NotImplementedError(NOT_BUILT)


def require_admin(user: User) -> None:
    """Raise `PermissionDenied` unless `user` is the Admin (AC28)."""
    raise NotImplementedError(NOT_BUILT)


def add_account(by: User, name: str, email: str) -> NewAccount:
    """Add an account with a temporary password it must change (AC22)."""
    raise NotImplementedError(NOT_BUILT)


def deactivate(by: User, account: User) -> None:
    """Switch an account off; never your own (AC23, AC24)."""
    raise NotImplementedError(NOT_BUILT)


def reactivate(by: User, account: User) -> None:
    """Switch an account back on (AC23)."""
    raise NotImplementedError(NOT_BUILT)


def give_new_password(by: User, account: User) -> str:
    """A new temporary password for someone else; returns it (AC25)."""
    raise NotImplementedError(NOT_BUILT)


def lift_lock(by: User, account: User) -> None:
    """Clear this account's wrong-password count (AC11)."""
    raise NotImplementedError(NOT_BUILT)


def password_chosen(user: User) -> None:
    """The person saved their own password: no change is due any more."""
    raise NotImplementedError(NOT_BUILT)


def change_is_due(user: User) -> bool:
    """True while the person must choose their own password (AC25)."""
    raise NotImplementedError(NOT_BUILT)


def new_temporary_password(account: User) -> str:
    """Twelve letters and digits without look-alikes, in groups of four (§7.3)."""
    raise NotImplementedError(NOT_BUILT)


# ---------------------------------------------------------------------- lock


def client_address(request: HttpRequest) -> str | None:
    """Where a login came from (§7.2), or None when it can't be told."""
    raise NotImplementedError(NOT_BUILT)


def login_lock(email: str, address: str | None) -> bool:
    """True when this email, or this network address, has tried too often."""
    raise NotImplementedError(NOT_BUILT)


def locked_until(email: str) -> datetime | None:
    """When this email's lock lifts by itself, or None if it isn't locked."""
    raise NotImplementedError(NOT_BUILT)


def login_failed(email: str, address: str | None) -> None:
    """Count one wrong try. Never given the password."""
    raise NotImplementedError(NOT_BUILT)


def login_succeeded(email: str) -> None:
    """Clear this email's count, and tidy up old rows (§7.5)."""
    raise NotImplementedError(NOT_BUILT)
