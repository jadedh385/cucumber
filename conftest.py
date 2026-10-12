"""Test fixtures shared by every app (U0.3 design §5)."""

from collections.abc import Iterator

import psycopg
import pytest
from django.db import connection

from cucumber.env import env

APP_ROLE = "cucumber_app"

# Row builders and fixtures for the schema tests (U0.2a).
pytest_plugins = ["cucumber.core.tests.rows"]


@pytest.fixture
def app_db(transactional_db: None) -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    """A connection to the test database as the app user, `cucumber_app`.

    Use it to prove what the running app may and may not do (U0.2 design §4).
    It is a separate psycopg connection, not a Django alias, because Django can
    hand a "mirror" alias the main connection inside a test (U0.2 re-check N4).

    It asks for `transactional_db`, so rows a test writes through Django are
    committed and visible here. The connection is closed afterwards so it
    can't block pytest-django from clearing or dropping the test database.
    """
    password = env("DB_APP_PASSWORD")
    if not password:
        pytest.fail("DB_APP_PASSWORD is not set: copy .env.example to .env")
    settings = connection.settings_dict
    app_connection = psycopg.connect(
        dbname=settings["NAME"],
        user=APP_ROLE,
        password=password,
        host=settings["HOST"],
        port=settings["PORT"],
        autocommit=True,
    )
    try:
        current = app_connection.execute("SELECT current_user").fetchone()
        assert current == (APP_ROLE,), f"app_db connected as {current}"
        yield app_connection
    finally:
        app_connection.close()
