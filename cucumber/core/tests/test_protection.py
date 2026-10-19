"""U0.2a: database-level protection (design §4; AC6, AC13, AC19, AC20).

Two layers, each tested on its own:
- **Triggers** stop even the table owner (`cucumber_owner`, the role Django
  runs tests as) from editing or deleting history.
- **Grants**: the app user (`cucumber_app`) is never given UPDATE, DELETE or
  TRUNCATE where the design withholds them, checked live through `app_db`
  and as a full table-by-table matrix.
"""

import json

import pytest

from cucumber.core.tests.rows import (
    AppConnection,
    db_now,
    fetch_all,
    fetch_one,
    give_sku,
    insert,
    make_batch,
    make_event,
    make_review,
    make_vendor,
    quote,
    refused_by,
    refused_for_app,
    run,
)
from cucumber.core.tests.schema_spec import (
    INSERT_ONLY_TABLES,
    NO_DELETE_TABLES,
    REFERENCE_TABLES,
)

ALL_PRIVILEGES = [
    "SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER",
]  # fmt: skip
READ_WRITE = {"SELECT", "INSERT", "UPDATE"}
HOUSEKEEPING = {"SELECT", "INSERT", "UPDATE", "DELETE"}
# U0.4a design §7: the app may switch a flag and its groups, never create one.
FLAG_GRANTS = {
    "waffle_flag": {"SELECT", "UPDATE"},
    "waffle_flag_groups": {"SELECT", "INSERT", "DELETE"},
    "waffle_flag_users": {"SELECT"},
    "waffle_switch": {"SELECT"},
    "waffle_sample": {"SELECT"},
}
# U0.5 design §3.2: lock counts and change-due marks are added and removed,
# never edited.
ACCOUNT_GRANTS = {
    "accounts_login_failure": {"SELECT", "INSERT", "DELETE"},
    "accounts_password_change_due": {"SELECT", "INSERT", "DELETE"},
}

# Design §4, "App user permissions". Every table in the database must be listed:
# a new table without a decision here fails the matrix test.
APP_GRANTS: dict[str, set[str]] = (
    {table: {"SELECT", "INSERT"} for table in INSERT_ONLY_TABLES}
    | {table: READ_WRITE for table in NO_DELETE_TABLES}
    | {
        "auth_user": READ_WRITE,
        "django_session": HOUSEKEEPING,
        "django_admin_log": HOUSEKEEPING,
        "auth_user_groups": HOUSEKEEPING,
        "auth_user_user_permissions": HOUSEKEEPING,
        "auth_group": {"SELECT"},
        "auth_permission": {"SELECT"},
        "auth_group_permissions": {"SELECT"},
        "django_content_type": {"SELECT"},
        "django_migrations": {"SELECT"},
    }
    | FLAG_GRANTS
    | ACCOUNT_GRANTS
)

# A harmless column to "update" on each insert-only table.
UNCHANGED_COLUMN = {
    "events": "note",
    "operations": "recorded_at",
    "event_reviews": "note",
    "plant_status_changes": "reason",
    "skus": "assigned_at",
    "audit_log": "reason",
}

# Each reference table's first code and a valid new one (None: any seeded code).
RENAMES = {
    "genera": ("PHL", "PHZ"),
    "stages": ("P2", "P9"),
    "media_codes": ("M001", "M999"),
    "locations": ("lab", "lab2"),
    "reasons": (None, "renamed"),
}


@pytest.fixture
def one_row_everywhere(user: int, reviewer: int, plant: int) -> None:
    """At least one row in every protected table, so row triggers fire.

    Also proves these tests run as the tables' owner, as AC13 requires.
    """
    owners = fetch_all(
        "SELECT DISTINCT tableowner = current_user FROM pg_tables"
        " WHERE schemaname = 'public' AND tablename = ANY(%s)",
        [[*INSERT_ONLY_TABLES, *NO_DELETE_TABLES]],
    )
    assert owners == [(True,)], "tests must run as the owner of the tables"
    give_sku(plant, "PHL001", user)
    status_change = {
        "plant_id": plant,
        "from_status": "collection",
        "to_status": "portfolio",
        "sku_assigned": "PHL001",
        "changed_by": user,
        "changed_at": db_now(),
        "reason": None,
    }
    insert("plant_status_changes", status_change)
    batch = make_batch(plant, user)
    make_review(make_event(batch, user, "count", counted_qty=0), reviewer)
    make_vendor()
    audit = {
        "actor_id": user,
        "at": db_now(),
        "table_name": "plants",
        "row_pk": str(plant),
        "action": "insert",
        "before": None,
        "after": json.dumps({"full_name": "Pink Princess"}),
        "reason": None,
    }
    insert("audit_log", audit)


# ---------------------------------------------------- triggers stop the owner


@pytest.mark.django_db
@pytest.mark.usefixtures("one_row_everywhere")
@pytest.mark.parametrize("table", INSERT_ONLY_TABLES)
def test_owner_cannot_update_history(table: str) -> None:
    """AC13 (events), AC19 (reviews), and every other insert-only table."""
    column = quote(UNCHANGED_COLUMN[table])
    with refused_by(f"{table}_append_only"):
        run(f"UPDATE {quote(table)} SET {column} = {column}")  # noqa: S608


@pytest.mark.django_db
@pytest.mark.usefixtures("one_row_everywhere")
@pytest.mark.parametrize("table", INSERT_ONLY_TABLES)
def test_owner_cannot_delete_history(table: str) -> None:
    with refused_by(f"{table}_append_only"):
        run(f"DELETE FROM {quote(table)}")  # noqa: S608


@pytest.mark.django_db
@pytest.mark.usefixtures("one_row_everywhere")
@pytest.mark.parametrize("table", NO_DELETE_TABLES)
def test_owner_cannot_delete_plants_batches_or_lists(table: str) -> None:
    """AC6 (plants), AC20 (reference lists), rule 9 (batches)."""
    with refused_by(f"{table}_no_delete"):
        run(f"DELETE FROM {quote(table)}")  # noqa: S608


@pytest.mark.django_db
@pytest.mark.parametrize("table", REFERENCE_TABLES)
def test_reference_codes_cannot_be_renamed(table: str) -> None:
    """AC20: codes are permanent, so history stays readable."""
    old, new = RENAMES[table]
    if old is None:
        old = str(fetch_one(f"SELECT min(code) FROM {quote(table)}")[0])  # noqa: S608
    with refused_by(f"{table}_code_rename"):
        run(f"UPDATE {quote(table)} SET code = %s WHERE code = %s", [new, old])  # noqa: S608


# ------------------------------------------------ the app user is not allowed
#
# A few live refusals for the ACs that name the app user. The grants matrix
# below covers every other table. Kept few on purpose: each `app_db` test
# flushes the database afterwards, seed rows included (see `app_db`).

APP_REFUSALS = [
    "DELETE FROM plants",  # AC6
    "UPDATE events SET note = note",  # AC13
    "DELETE FROM events",  # AC13
    "TRUNCATE events",
    "UPDATE event_reviews SET note = note",  # AC19
    "DELETE FROM event_reviews",  # AC19
]


@pytest.mark.parametrize("statement", APP_REFUSALS)
def test_app_user_is_refused(app_db: AppConnection, statement: str) -> None:
    """AC6, AC13, AC19: refused by grants, before any trigger runs."""
    refused_for_app(app_db, statement)


# -------------------------------------------------------------- grants matrix


def app_privileges(table: str) -> set[str]:
    return {
        privilege
        for privilege in ALL_PRIVILEGES
        if fetch_one(
            "SELECT has_table_privilege('cucumber_app', %s, %s)",
            [f"public.{table}", privilege],
        )[0]
    }


def public_tables() -> list[str]:
    rows = fetch_all(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY 1"
    )
    return [str(row[0]) for row in rows]


@pytest.mark.django_db
def test_every_domain_table_exists() -> None:
    domain_tables = set(INSERT_ONLY_TABLES) | set(NO_DELETE_TABLES)
    assert sorted(domain_tables - set(public_tables())) == []


@pytest.mark.django_db
def test_every_table_has_a_grant_decision() -> None:
    """A new table must be added to design §4 and APP_GRANTS on purpose."""
    assert sorted(set(public_tables()) - set(APP_GRANTS)) == []


@pytest.mark.django_db
def test_app_user_grants_match_the_design_exactly() -> None:
    """Design §4 (H3): no missed grant and no extra one, TRUNCATE on nothing."""
    actual = {table: app_privileges(table) for table in public_tables()}
    wrong = {
        table: sorted(privileges)
        for table, privileges in actual.items()
        if privileges != APP_GRANTS.get(table, privileges)
    }
    assert wrong == {}


@pytest.mark.django_db
def test_app_user_may_use_every_sequence_but_not_reset_it() -> None:
    rows = fetch_all(
        "SELECT name,"
        " has_sequence_privilege('cucumber_app', name, 'USAGE'),"
        " has_sequence_privilege('cucumber_app', name, 'SELECT'),"
        " has_sequence_privilege('cucumber_app', name, 'UPDATE')"
        " FROM (SELECT schemaname || '.' || sequencename AS name"
        "       FROM pg_sequences WHERE schemaname = 'public') AS sequences"
    )
    assert rows, "no sequences: the identity columns are missing"
    wrong = [row[0] for row in rows if row[1:] != (True, True, False)]
    assert wrong == []


@pytest.mark.django_db
def test_new_tables_get_select_and_insert_by_default() -> None:
    """Design §4: ALTER DEFAULT PRIVILEGES, so a new table is never left out."""
    run(
        "CREATE TABLE default_grants_probe (id bigint GENERATED BY DEFAULT AS IDENTITY)"
    )
    assert app_privileges("default_grants_probe") == {"SELECT", "INSERT"}
    sequence = fetch_one(
        "SELECT has_sequence_privilege('cucumber_app',"
        " pg_get_serial_sequence('default_grants_probe', 'id'), 'USAGE')"
    )
    assert sequence == (True,)
