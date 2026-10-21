"""Logging in by email and password, with the re-hash written as System (U0.7 §4.3).

Django's `ModelBackend` re-hashes a right password that was stored with an
older setting, and saves it during `authenticate`. That one write is System's,
so `audited()` is opened here, around it alone (G4 review, item 8), not around
every login try.
"""

import logging
from typing import Any

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpRequest

from cucumber.core.audit import SYSTEM, VIA_LOGIN, audited

logger = logging.getLogger(__name__)


def save_new_hash(user: User, raw_password: str) -> None:
    """Re-hash for `user` as System; with no System account, leave it as it is.

    Never a write without a name. The hash is tried again at the next login.
    The in-memory user changes only once the write has, so the session (tied
    to the stored hash) stays valid.
    """
    hashed = make_password(raw_password)
    try:
        with audited(SYSTEM, via=VIA_LOGIN):
            User.objects.filter(pk=user.pk).update(password=hashed)
    except ObjectDoesNotExist:
        logger.error("password not re-hashed: the System account is missing")
        return
    user.password = hashed


class AuditedRehashBackend(ModelBackend):
    def authenticate(
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        **kwargs: Any,
    ) -> User | None:
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
        if username is None or password is None:
            return None
        try:
            user = User._default_manager.get_by_natural_key(username)
        except User.DoesNotExist:
            # One hash anyway, so a missing email takes as long as a wrong one.
            User().set_password(password)
            return None

        def rehash(raw_password: str) -> None:
            save_new_hash(user, raw_password)

        if check_password(password, user.password, rehash):
            return user if self.user_can_authenticate(user) else None
        return None
