"""Naming who makes a change, for the audit trail (U0.7 design §3, §9).

The database writes the trail: a trigger on every audited table adds one
`audit_log` row per change, in the change's own transaction. `audited()`
tells it who is making the change, and why when a reason is needed. A change
to an audited table with nobody named is refused (`audit_actor_required`).
"""

import getpass
import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from django.contrib.auth.models import User
from django.db import connection, transaction

from cucumber.core.refusals import refuse
from cucumber.references.models import Reason as ListedReason

# Design §5.2: the reserved account for SSH commands and migrations.
SYSTEM_USERNAME = "system@cucumber.invalid"
# Design §3.1: the longest reason note, after trimming.
LONGEST_NOTE = 500

# Design §3.1, Q2: how the change was made, when not through a page.
VIA_APP = "app"
VIA_LOGIN = "login"
VIA_MIGRATION = "migration"


def printable(text: str) -> str:
    """`text` without control characters: an environment value can't dress up a row."""
    return "".join(char for char in text if char.isprintable()).strip()


def process_user() -> str:
    try:
        return getpass.getuser()
    except (KeyError, OSError):
        return "unknown"


def ssh_via(command: str) -> str:
    """`via` for a command run over SSH: who ran it, and from where (review #3).

    Every such command acts as System, so the person is only in `via`. The
    container can't see the SSH session: the runbook and `scripts/flag.py`
    pass `SSH_USER` and `SSH_CONNECTION` in.
    """
    user = printable(os.environ.get("SSH_USER", "")) or process_user()
    connection = printable(os.environ.get("SSH_CONNECTION", ""))
    where = f"ssh {connection}" if connection else "no ssh connection"
    return f"{command} by {user} ({where})"


@dataclass(frozen=True)
class Reason:
    """A reason code from the `reasons` list, plus an optional note (AC11)."""

    code: str
    note: str = ""


# Design §7.2: only `cucumber_anonymise` uses it (inactive on the list).
PDPA_REQUEST = Reason("deactivate_pdpa_request")


class SystemActor:
    """Stands for the System account, looked up again on every use (review H2)."""

    def __repr__(self) -> str:
        return "SYSTEM"


SYSTEM = SystemActor()


def system_account() -> User:
    """The System account (design §5.2), read from the database each call."""
    return User.objects.get(username=SYSTEM_USERNAME)


# The four settings the audit and reason triggers read (design §2).
SETTINGS = ("actor_id", "via", "reason_code", "note")
READ_SETTINGS = "SELECT " + ", ".join(
    f"coalesce(current_setting('cucumber.{name}', true), '')" for name in SETTINGS
)
WRITE_SETTINGS = "SELECT " + ", ".join(
    f"set_config('cucumber.{name}', %s, true)" for name in SETTINGS
)

# The people named by the `audited()` blocks open now, innermost last.
_named: ContextVar[tuple[int, ...]] = ContextVar("audited_named", default=())


def checked_note(reason: Reason | None) -> str:
    """The reason's note, trimmed; `reason_note_too_long` past 500 characters."""
    note = reason.note.strip() if reason else ""
    if len(note) > LONGEST_NOTE:
        raise refuse("reason_note_too_long")
    return note


def require_reason(reason: Reason | None, reason_list: str) -> Reason:
    """The service side of the reason rule, checked before anything is written.

    Design §4.2, §6: no reason is `reason_required`; a code that isn't active
    on `reason_list` is `reason_wrong_list` (so a page can't pick an inactive
    one, like the PDPA reason); a long note is `reason_note_too_long`.
    """
    if reason is None or not reason.code.strip():
        raise refuse("reason_required")
    listed = ListedReason.objects.filter(
        pk=reason.code, applies_to=reason_list, active=True
    )
    if not listed.exists():
        raise refuse("reason_wrong_list")
    checked_note(reason)
    return reason


def actor_id(by: User | SystemActor) -> int:
    return system_account().pk if isinstance(by, SystemActor) else by.pk


def read_settings() -> list[str]:
    with connection.cursor() as cursor:
        cursor.execute(READ_SETTINGS)
        row = cursor.fetchone()
    return [str(value) for value in row]


def write_settings(values: list[str]) -> None:
    with connection.cursor() as cursor:
        cursor.execute(WRITE_SETTINGS, values)


@contextmanager
def audited(
    by: User | SystemActor,
    *,
    via: str | None = None,
    reason: Reason | None = None,
) -> Iterator[None]:
    """A transaction in which every audited write names `by` (design §3).

    Opens `transaction.atomic()` and sets the four `cucumber.*` settings for
    it. On the way out, normal or not, it puts back the values that were
    there before (usually empty). Nested for a different person it raises
    (a programming error, not a refusal).

    A nested block is the same change: without a `reason` or `via` it keeps
    the outer block's, and a different reason raises (G4 review, item 9).

    Inside an outer transaction `atomic()` is a savepoint, and releasing one
    keeps `set_config(…, true)` values, so they are put back by hand (review
    H1). After an error the savepoint is rolled back, which puts them back.
    """
    note = checked_note(reason)
    person = actor_id(by)
    outer = _named.get()
    if outer and outer[-1] != person:
        raise RuntimeError(
            f"audited() for account {person} inside audited() for {outer[-1]}:"
            " one change has one person."
        )
    token = _named.set((*outer, person))
    try:
        with transaction.atomic():
            previous = read_settings()
            write_settings(
                nested_values(person, via, reason, note, previous, bool(outer))
            )
            yield
            write_settings(previous)
    finally:
        _named.reset(token)


def nested_values(
    person: int,
    via: str | None,
    reason: Reason | None,
    note: str,
    previous: list[str],
    is_nested: bool,
) -> list[str]:
    """The four settings for a block: its own, else the outer block's."""
    _, outer_via, outer_code, outer_note = previous if is_nested else ["", "", "", ""]
    if reason is None:
        code, note = outer_code, outer_note
    elif outer_code and reason.code != outer_code:
        raise RuntimeError(
            f"audited() with reason {reason.code} inside audited() with reason"
            f" {outer_code}: one change has one reason."
        )
    else:
        code = reason.code
    return [str(person), via or outer_via or VIA_APP, code, note]


# ------------------------------------------------------------- AC17, §9

AUDITED = frozenset(
    {
        "plants",
        "batches",
        "genera",
        "stages",
        "media_codes",
        "locations",
        "reasons",
        "container_types",  # U0.9
        "vendors",
        "auth_user",
        "auth_user_groups",
        "waffle_flag",
        "waffle_flag_groups",
    }
)
OWN_RECORD = "append-only; its own record"
READ_ONLY = "read-only to the app"
NOT_AUDITED = {  # table: why
    "events": OWN_RECORD,
    "operations": OWN_RECORD,
    "event_reviews": OWN_RECORD,
    "plant_status_changes": OWN_RECORD,
    "skus": OWN_RECORD,
    "audit_log": "the trail itself",
    "django_session": "housekeeping",
    "accounts_login_failure": "housekeeping; logins stay in the app log (spec Q2)",
    "accounts_password_change_due": "housekeeping; the password change is on auth_user",
    "auth_user_user_permissions": READ_ONLY
    + " (U0.7 revokes writes; roles are groups)",
    "auth_group": READ_ONLY,
    "auth_permission": READ_ONLY,
    "auth_group_permissions": READ_ONLY,
    "django_content_type": READ_ONLY,
    "django_migrations": READ_ONLY,
    "waffle_flag_users": READ_ONLY,
    "waffle_switch": READ_ONLY,
    "waffle_sample": READ_ONLY,
}
