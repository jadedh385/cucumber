"""What happens at every login and logout, however it was done (design §5, §8).

Connected in AccountsConfig.ready().
"""

import logging
import time
from typing import Any

from django.contrib.auth.models import AnonymousUser, User
from django.http import HttpRequest

from cucumber.accounts.middleware import LOGIN_AT

logger = logging.getLogger(__name__)


def stamp_login(
    sender: type[User], request: HttpRequest | None, user: User, **kwargs: Any
) -> None:
    """Note when this session logged in, for the 30-day limit (AC13).

    Django has already given the session a new id by now (AC15).
    """
    if request is not None:
        request.session[LOGIN_AT] = int(time.time())
    logger.info("login ok account=%s", user.pk)


def note_logout(
    sender: type[User] | None,
    request: HttpRequest | None,
    user: User | AnonymousUser | None,
    **kwargs: Any,
) -> None:
    if user is not None and user.is_authenticated:
        logger.info("logout account=%s", user.pk)
