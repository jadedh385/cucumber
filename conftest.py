"""Test fixtures shared by every app (U0.3 design §5)."""

from collections.abc import Iterator

import psycopg
import pytest
from django.db import connection

from cucumber.env import env

APP_ROLE = "cucumber_app"

# Row builders for the schema tests (U0.2a); staff and stock for the
# service tests (U0.2b); audit rows (U0.7).
pytest_plugins = [  # each before the ones that import it
    "cucumber.core.tests.rows",
    "cucumber.core.tests.trail",
    "cucumber.core.tests.stock",
]


@pytest.fixture
def app_db(transactional_db: None) -> Iterator[psycopg.Connection[tuple[object, ...]]]:
    """A connection to the test database as the app user, `cucumber_app`.

    Use it to prove what the running app may and may not do (U0.2 design §4).
    It is a separate psycopg connection, not a Django alias, because Django can
    hand a "mirror" alias the main connection inside a test (U0.2 re-check N4).

    It asks for `transactional_db`, so rows a test writes through Django are
    committed and visible here. Afterwards the whole test database is
    flushed, seed rows from data migrations included; pytest-django runs
    these tests after the others, so the seed tests still see them. A test
    here that needs seed rows must insert its own.

    The connection is closed afterwards so it can't block pytest-django from
    clearing or dropping the test database.
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


@pytest.fixture
def as_app_user() -> Iterator[None]:
    """Django's own connection, as `cucumber_app`, until the test ends.

    The other tests run as the tables' owner, so a service that works as the
    owner could still fail on the servers (U0.5 design §9). Ask for it after
    the fixtures that set up rows as the owner; it logs back in as the owner
    afterwards, so pytest-django can empty the database. Committing tests
    only (`django_db(transaction=True)`).
    """
    password = env("DB_APP_PASSWORD")
    if not password:
        pytest.fail("DB_APP_PASSWORD is not set: copy .env.example to .env")
    settings = connection.settings_dict
    owner = (settings["USER"], settings["PASSWORD"])
    connection.close()
    settings["USER"], settings["PASSWORD"] = APP_ROLE, password
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            assert cursor.fetchone() == (APP_ROLE,)
        yield
    finally:
        connection.close()
        settings["USER"], settings["PASSWORD"] = owner
