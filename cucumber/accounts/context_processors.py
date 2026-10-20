"""What the person may do, for the templates (U0.6 design §3.3, AC11)."""

from django.http import HttpRequest

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
