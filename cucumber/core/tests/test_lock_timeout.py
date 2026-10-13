"""AC8: a save waiting on another save's lock gives up instead of hanging.

The app's connection sets `lock_timeout = 5s` (U0.4a design §5). Nothing is
saved when it gives up.
"""

import threading
import time
from collections.abc import Iterator

import psycopg
import pytest
from django.contrib.auth.models import Group
from django.db import OperationalError, connection

LOCK_TIMEOUT_SECONDS = 5
# If the timeout is missing, the lock is let go after this long, so the test
# fails instead of hanging.
SAFETY_RELEASE_SECONDS = 15


def test_the_apps_connection_has_the_lock_timeout(db: None) -> None:
    with connection.cursor() as cursor:
        cursor.execute("SHOW lock_timeout")
        row = cursor.fetchone()

    assert row == (f"{LOCK_TIMEOUT_SECONDS}s",)


@pytest.fixture
def other_connection(
    transactional_db: None,
) -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    """A second connection to the test database, as another save would be."""
    settings = connection.settings_dict
    other = psycopg.connect(
        dbname=settings["NAME"],
        user=settings["USER"],
        password=settings["PASSWORD"],
        host=settings["HOST"],
        port=settings["PORT"],
    )
    try:
        yield other
    finally:
        other.rollback()
        other.close()


def test_a_save_blocked_by_a_row_lock_gives_up_after_the_timeout(
    other_connection: psycopg.Connection[tuple[object, ...]],
) -> None:
    group = Group.objects.create(name="before")
    other_connection.execute(
        "SELECT 1 FROM auth_group WHERE id = %s FOR UPDATE", (group.pk,)
    )
    safety = threading.Timer(SAFETY_RELEASE_SECONDS, other_connection.rollback)
    safety.start()
    started = time.monotonic()
    try:
        with pytest.raises(OperationalError, match="lock timeout"):
            Group.objects.filter(pk=group.pk).update(name="after")
        waited = time.monotonic() - started
    finally:
        safety.cancel()

    assert LOCK_TIMEOUT_SECONDS - 0.5 <= waited < SAFETY_RELEASE_SECONDS
    other_connection.rollback()
    assert Group.objects.get(pk=group.pk).name == "before"
