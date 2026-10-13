"""AC6, AC13: the app user may switch a flag but not create one (design §7).

`cucumber_flag` runs as `cucumber_app`, so the owner password stays with the
migration step. Migration `core 0005` gives it exactly FLAG_GRANTS on
Waffle's tables (checked with every other table in test_protection.py);
undoing it puts U0.2a's defaults back.
"""

from collections.abc import Iterator
from typing import Any

import psycopg
import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.db import connection
from waffle.models import Flag

from cucumber.core.tests.rows import refused_for_app
from cucumber.core.tests.test_protection import FLAG_GRANTS

AppConnection = psycopg.Connection[tuple[object, ...]]

RIGHTS = ["SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"]
# What U0.2a's default privileges give any new table (core 0003).
DEFAULT_RIGHTS = {"SELECT", "INSERT"}
BEFORE_GRANTS = "0004_refuse_reverse_with_data"
# Every column Waffle requires, so only the missing right can refuse it.
NEW_FLAG = (
    "INSERT INTO waffle_flag (name, testing, superusers, staff, authenticated,"
    " languages, rollout, note, created, modified)"
    " VALUES ('typo', false, false, false, false, '', false, '', now(), now())"
)


def app_has(table: str, right: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT has_table_privilege('cucumber_app', %s, %s)", [table, right]
        )
        return bool(cursor.fetchone() == (True,))


def app_rights(table: str) -> set[str]:
    return {right for right in RIGHTS if app_has(table, right)}


@pytest.fixture
def flag(transactional_db: None) -> Any:
    return Flag.objects.create(name="needs_attention", everyone=False)


def test_the_app_can_switch_a_flag_and_its_groups(
    flag: Any, app_db: AppConnection
) -> None:
    group = Group.objects.create(name="Owner")

    app_db.execute("UPDATE waffle_flag SET everyone = NULL WHERE id = %s", [flag.pk])
    app_db.execute(
        "INSERT INTO waffle_flag_groups (flag_id, group_id) VALUES (%s, %s)",
        [flag.pk, group.pk],
    )
    app_db.execute("DELETE FROM waffle_flag_groups WHERE flag_id = %s", [flag.pk])


def test_the_app_can_not_create_or_delete_a_flag(
    flag: Any, app_db: AppConnection
) -> None:
    refused_for_app(app_db, NEW_FLAG)
    refused_for_app(app_db, f"DELETE FROM waffle_flag WHERE id = {flag.pk}")  # noqa: S608


@pytest.fixture
def grants_undone(transactional_db: None) -> Iterator[None]:
    call_command("migrate", "core", BEFORE_GRANTS, verbosity=0)
    try:
        yield
    finally:
        call_command("migrate", "core", verbosity=0)


def test_undoing_the_grants_puts_the_defaults_back(grants_undone: None) -> None:
    for table in FLAG_GRANTS:
        assert app_rights(table) == DEFAULT_RIGHTS, table


def test_the_grants_migration_runs_forward_again(grants_undone: None) -> None:
    call_command("migrate", "core", verbosity=0)

    for table, rights in FLAG_GRANTS.items():
        assert app_rights(table) == rights, table
