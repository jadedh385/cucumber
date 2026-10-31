"""The menu: the bottom bar on a phone, the side menu on a desktop (U0.10a §6.2, AC5).

Each item names the matrix row that decides who sees it, the same row its
page is labelled with (`allowed_for`), so the menu can't show a page that
refuses the person or hide one that lets them in.
"""

from dataclasses import dataclass

from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _

from cucumber.accounts.permissions import Permission


@dataclass(frozen=True)
class MenuItem:
    label: str | Promise
    url_name: str
    permission: Permission  # the matrix row that decides who sees it
    icon: str
    marks: frozenset[str]  # url names on which this item is "current"
    on_production: bool = True  # False: local and staging only


MENU: tuple[MenuItem, ...] = (
    MenuItem(_("Home"), "home", Permission.OWN_ACCOUNT, "home", frozenset({"home"})),
    MenuItem(
        _("Staff"),
        "staff",
        Permission.MANAGE_USERS,
        "users",
        frozenset({"staff", "staff_new", "staff_detail"}),
    ),
    MenuItem(
        _("Practice"),
        "practice",
        Permission.OWN_ACCOUNT,
        "beaker",
        frozenset({"practice"}),
        on_production=False,
    ),  # Q4 a); in the §12 wireframe's bar
    MenuItem(
        _("Account"),
        "account",
        Permission.OWN_ACCOUNT,
        "user",
        frozenset({"account", "password"}),
    ),  # Q3 a)
)
