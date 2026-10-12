"""Rules for the accounts app. Views call these; they never hold rules themselves.

A role is a Django group (U0.2 design §2.7); the permission matrix is U0.6.
"""

from django.contrib.auth.models import User

ADMIN = "admin"
SUPERVISOR = "supervisor"
TECH = "tech"


def has_role(user: User, role: str) -> bool:
    """True when `user` is in the role's group."""
    return user.groups.filter(name=role).exists()


def members_of(role: str) -> frozenset[int]:
    """The ids of every user in the role's group."""
    return frozenset(
        User.objects.filter(groups__name=role).values_list("id", flat=True)
    )
