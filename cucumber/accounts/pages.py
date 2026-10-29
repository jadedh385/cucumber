"""What the Staff pages show, built from service data (U0.10a §10.2).

Presentation only: which fact goes in which cell of the kit's `Table` and
`Detail`. The rules stay in services.py; the templates only lay these out.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from django.contrib.auth.models import User
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import time_format
from django.utils.translation import gettext as _

from cucumber.accounts import services
from cucumber.accounts.forms import ROLE_LABELS
from cucumber.accounts.permissions import Role
from cucumber.core.kit import Column, Detail, Empty, Fact, Row, Table

LOCK_TIME_FORMAT = "H:i"


@dataclass(frozen=True)
class StaffRow:
    """One account as the Staff pages show it."""

    account: User
    is_you: bool
    locked_until: datetime | None
    role: Role | None
    is_anonymised: bool = False

    @property
    def role_label(self) -> str:
        return str(ROLE_LABELS[self.role]) if self.role else _("No role")


def staff_row(
    request: HttpRequest,
    account: User,
    role: Role | None,
    locked_until: datetime | None,
) -> StaffRow:
    return StaffRow(
        role=role,
        account=account,
        is_you=account.pk == request.user.pk,
        locked_until=locked_until,
        is_anonymised=services.is_anonymised(account),
    )


def name_of(account: User) -> str:
    return account.first_name or account.email


def state_text(row: StaffRow) -> str:
    """`Active`, `Deactivated`, then ` · Locked until 14:05` while locked."""
    state = _("Active") if row.account.is_active else _("Deactivated")
    if row.locked_until is None:
        return state
    time = time_format(timezone.localtime(row.locked_until), LOCK_TIME_FORMAT)
    return f"{state} · {_('Locked until %(time)s') % {'time': time}}"


def staff_table(rows: Sequence[StaffRow]) -> Table:
    """The Staff list: Name (main, `(you)` on your own), Email, Role, State."""
    return Table(
        columns=(
            Column(_("Name"), is_main=True),
            Column(_("Email")),
            Column(_("Role")),
            Column(_("State")),
        ),
        rows=tuple(
            Row(
                cells=(
                    f"{name_of(row.account)} {_('(you)')}"
                    if row.is_you
                    else name_of(row.account),
                    row.account.email,
                    row.role_label,
                    state_text(row),
                ),
                href=reverse("staff_detail", args=[row.account.pk]),
            )
            for row in rows
        ),
        empty=Empty(
            _("No staff yet. Add the first person."), _("Add"), reverse("staff_new")
        ),
    )


def staff_detail(row: StaffRow) -> Detail:
    """A person's page: their name, then Email, Role and State."""
    return Detail(
        title=name_of(row.account),
        facts=(
            Fact(_("Email"), row.account.email),
            Fact(_("Role"), row.role_label),
            Fact(_("State"), state_text(row)),
        ),
    )
