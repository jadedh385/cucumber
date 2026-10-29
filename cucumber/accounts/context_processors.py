"""What the person may do, and the menu, for the templates (U0.6 §3.3, U0.10a §6.2)."""

from django.conf import settings
from django.http import HttpRequest

from cucumber.accounts.menu import MENU, MenuItem
from cucumber.accounts.permissions import MATRIX, Permission, Standing, may, standing

PRODUCTION = "production"


def standing_of(request: HttpRequest) -> Standing:
    """`request.standing`, or read now when a page skipped RoleRequired (one query).

    404 and the CSRF page skip it. The reading is kept on the request, so the
    menu and `allowed` share the one query.
    """
    current = getattr(request, "standing", None)
    if current is None:
        current = standing(request.user)
        request.standing = current  # type: ignore[attr-defined]
    return current


def permissions(request: HttpRequest) -> dict[str, frozenset[Permission]]:
    """`allowed`: the person's permissions; empty for nobody signed in."""
    current = standing_of(request)
    if not current.is_active:
        return {"allowed": frozenset()}
    return {
        "allowed": frozenset(
            row.permission for row in MATRIX if may(current.role, row.permission)
        )
    }


def menu(request: HttpRequest) -> dict[str, tuple[MenuItem, ...]]:
    """`menu`: the `MENU` items the person may open, in order (U0.10a §6.2, AC5).

    Nobody signed in: no items. Practice only off production.
    """
    current = standing_of(request)
    if not current.is_active:
        return {"menu": ()}
    on_production = settings.ENVIRONMENT == PRODUCTION
    return {
        "menu": tuple(
            item
            for item in MENU
            if may(current.role, item.permission)
            and (item.on_production or not on_production)
        )
    }
