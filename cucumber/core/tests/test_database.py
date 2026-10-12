"""AC8, AC9: tests run on real PostgreSQL 17 with Cucumber's two roles."""

import psycopg
import pytest
from django.db import connection

pytestmark = pytest.mark.django_db

POSTGRES_17 = 170000


def query_one(sql: str) -> object:
    with connection.cursor() as cursor:
        cursor.execute(sql)
        row = cursor.fetchone()
    assert row is not None
    return row[0]


def test_test_database_is_postgresql_17_not_sqlite() -> None:
    assert connection.vendor == "postgresql"
    assert int(str(query_one("SHOW server_version_num"))) >= POSTGRES_17


def test_init_script_created_both_roles() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT rolname FROM pg_roles WHERE rolname LIKE 'cucumber_%'")
        roles = {row[0] for row in cursor.fetchall()}
    assert roles == {"cucumber_owner", "cucumber_app"}


def test_app_user_has_no_special_powers() -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls"
            " FROM pg_roles WHERE rolname = 'cucumber_app'"
        )
        assert cursor.fetchone() == (False, False, False, False)


def test_django_runs_tests_as_the_owner() -> None:
    assert query_one("SELECT current_user") == "cucumber_owner"


def test_app_db_connects_as_the_app_user(
    app_db: psycopg.Connection[tuple[object, ...]],
) -> None:
    assert app_db.execute("SELECT current_user").fetchone() == ("cucumber_app",)


def test_app_db_uses_the_test_database(
    app_db: psycopg.Connection[tuple[object, ...]],
) -> None:
    row = app_db.execute("SELECT current_database()").fetchone()
    assert row == (connection.settings_dict["NAME"],)


def test_app_user_cannot_create_a_table(
    app_db: psycopg.Connection[tuple[object, ...]],
) -> None:
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app_db.execute("CREATE TABLE intruder (id integer)")
