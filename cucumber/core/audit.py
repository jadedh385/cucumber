"""Naming who makes a change, for the audit trail (U0.7 design §3, §9).

The database writes the trail: a trigger on every audited table adds one
`audit_log` row per change, in the change's own transaction. `audited()`
tells it who is making the change, and why when a reason is needed. A change
to an audited table with nobody named is refused (`audit_actor_required`).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from django.contrib.auth.models import User

# Design §5.2: the reserved account for SSH commands and migrations.
SYSTEM_USERNAME = "system@cucumber.invalid"
# Design §3.1: the longest reason note, after trimming.
LONGEST_NOTE = 500

# Design §3.1, Q2: how the change was made, when not through a page.
VIA_APP = "app"
VIA_LOGIN = "login"
VIA_MIGRATION = "migration"


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
    raise NotImplementedError("U0.7 G3")


@contextmanager
def audited(
    by: User | SystemActor,
    *,
    via: str = VIA_APP,
    reason: Reason | None = None,
) -> Iterator[None]:
    """A transaction in which every audited write names `by` (design §3).

    Opens `transaction.atomic()` and sets the four `cucumber.*` settings for
    it. On the way out, normal or not, it puts back the values that were
    there before (usually empty). Nested for a different person it raises
    (a programming error, not a refusal).
    """
    raise NotImplementedError("U0.7 G3")
    yield  # pragma: no cover


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
