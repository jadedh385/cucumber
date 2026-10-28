"""What the person may do, for the templates (U0.6 design §3.3, AC11)."""

from django.http import HttpRequest

from cucumber.accounts.menu import MenuItem
from cucumber.accounts.permissions import MATRIX, Permission, may


def permissions(request: HttpRequest) -> dict[str, frozenset[Permission]]:
    """`allowed`: the person's permissions, from `request.standing`.

    Pages that skip RoleRequired (login, 404, 500) get an empty set.
    """
    current = getattr(request, "standing", None)
    if current is None:
        return {"allowed": frozenset()}
    return {
        "allowed": frozenset(
            row.permission for row in MATRIX if may(current.role, row.permission)
        )
    }


def menu(request: HttpRequest) -> dict[str, tuple[MenuItem, ...]]:
    """`menu`: the `MENU` items the person may open, in order (U0.10a §6.2, AC5).

    Read from `request.standing`, or from `standing()` when a page skipped
    RoleRequired (404, CSRF page) and someone is signed in. Nobody signed in:
    no items. Practice only off production. G2 stub: built at G3.
    """
    raise NotImplementedError("U0.10a G3")
