"""AC15: `cucumber_check_guards` notices a protection switched off (design §8).

Each kind in §8.1 is broken one at a time inside the test's transaction,
which puts it back afterwards. Two kinds can't be broken here: making the
app role a superuser or giving it a role setting needs CREATEROLE, which the
tests' login (the owner) doesn't have, just as on the servers.
"""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from cucumber.core.guards import GUARDS, Kind
from cucumber.core.tests.rows import AppConnection, fetch_all, run
from cucumber.core.tests.trail import (
    accept_noticed_truncates,
    audit_mark,
    audit_rows_since,
    restore_audit_rows,
    system_id,
)

pytestmark = pytest.mark.django_db


def check() -> str:
    """The command's output when everything is on."""
    out = StringIO()
    call_command("cucumber_check_guards", stdout=out)
    return out.getvalue()


def failures() -> str:
    """The command's output when something is off; it must stop with an error."""
    out = StringIO()
    with pytest.raises(CommandError):
        call_command("cucumber_check_guards", stdout=out)
    return out.getvalue()


def accept(note: str) -> str:
    out = StringIO()
    call_command("cucumber_check_guards", "--accept", note, stdout=out)
    return out.getvalue()


def truncate(table: str) -> None:
    """The owner empties a table: the accepted exception, noticed (§4.4)."""
    run("SET CONSTRAINTS ALL IMMEDIATE")
    run(f"TRUNCATE {table}")
    run("SET CONSTRAINTS ALL DEFERRED")


def truncate_rows(table: str) -> list[int]:
    return [
        row.id
        for row in audit_rows_since(0)
        if row.action == "truncate" and row.table_name == table
    ]


@pytest.fixture(autouse=True)
def earlier_flushes_accepted() -> None:
    """A committing test's flush leaves `truncate` rows; they aren't this test's."""
    accept_noticed_truncates()


# --------------------------------------------------------- a fresh database
def test_a_freshly_migrated_database_passes() -> None:
    output = check().strip()

    assert GUARDS
    assert output.startswith("All ")
    assert output.endswith("protections on.")


def test_every_trigger_the_migrations_made_is_checked() -> None:
    """A new protection can't be left out of the check (design §8.1)."""
    triggers = {
        str(row[0])
        for row in fetch_all(
            "SELECT t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid = t.tgrelid"
            " JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE NOT t.tgisinternal AND n.nspname = 'public'"
        )
    }
    guarded = {guard.name for guard in GUARDS if guard.kind == Kind.TRIGGER}

    assert sorted(triggers - guarded) == []
    assert sorted(guarded - triggers) == []


def test_every_guard_names_the_migration_that_adds_it() -> None:
    assert [guard for guard in GUARDS if "." not in guard.migration] == []


# --------------------------------------------------- broken one at a time
BREAKS = {
    "trigger disabled": (
        "ALTER TABLE events DISABLE TRIGGER events_append_only",
        "events_append_only",
    ),
    "trigger replica only": (
        "ALTER TABLE plants ENABLE REPLICA TRIGGER plants_audit",
        "plants_audit",
    ),
    "trigger dropped": ("DROP TRIGGER plants_audit ON plants", "plants_audit"),
    "trigger arguments changed": (
        "DROP TRIGGER plants_audit ON plants;"
        " CREATE TRIGGER plants_audit AFTER INSERT OR UPDATE ON plants"
        " FOR EACH ROW EXECUTE FUNCTION"
        " cucumber_audit('id', 'name_key,full_name,notes,status', '')",
        "plants_audit",
    ),
    "trigger timing changed": (
        "DROP TRIGGER plants_audit ON plants;"
        " CREATE TRIGGER plants_audit AFTER INSERT ON plants"
        " FOR EACH ROW EXECUTE FUNCTION cucumber_audit('id', 'name_key', '')",
        "plants_audit",
    ),
    "trigger calls another function": (
        "DROP TRIGGER events_append_only ON events;"
        " CREATE TRIGGER events_append_only BEFORE UPDATE OR DELETE ON events"
        " FOR EACH ROW EXECUTE FUNCTION cucumber_code_rename()",
        "events_append_only",
    ),
    "function body changed": (
        "CREATE OR REPLACE FUNCTION cucumber_append_only() RETURNS trigger"
        " LANGUAGE plpgsql AS $$ BEGIN RETURN NEW; END $$",
        "cucumber_append_only",
    ),
    "function made security definer": (
        "ALTER FUNCTION cucumber_audit() SECURITY DEFINER",
        "cucumber_audit",
    ),
    "function search_path removed": (
        "ALTER FUNCTION cucumber_audit() RESET search_path",
        "cucumber_audit",
    ),
    "extra grant": ("GRANT UPDATE ON events TO cucumber_app", "events"),
    "missing grant": ("REVOKE INSERT ON plants FROM cucumber_app", "plants"),
    "column grant": ("GRANT UPDATE (note) ON events TO cucumber_app", "events"),
    "new table": ("CREATE TABLE guard_probe (id integer)", "guard_probe"),
    "temp tables": (
        "DO $$ BEGIN EXECUTE format("
        "'GRANT TEMP ON DATABASE %I TO cucumber_app', current_database()); END $$",
        "TEMP",
    ),
    "create in public": ("GRANT CREATE ON SCHEMA public TO cucumber_app", "CREATE"),
}


@pytest.mark.parametrize("name", sorted(BREAKS))
def test_each_kind_of_break_is_reported_by_name(name: str) -> None:
    statement, named = BREAKS[name]
    run(statement)

    output = failures()

    lines = [line for line in output.splitlines() if line.strip()]
    assert any(named in line for line in lines), output
    assert not any("protections on." in line for line in lines)


def test_two_breaks_are_two_lines() -> None:
    run("ALTER TABLE events DISABLE TRIGGER events_append_only")
    run("GRANT UPDATE ON skus TO cucumber_app")

    lines = failures().splitlines()

    assert any("events_append_only" in line for line in lines)
    assert any("skus" in line and "events_append_only" not in line for line in lines)


# ------------------------------------------------------ TRUNCATE (§4.4, §8.2)
def test_a_noticed_truncate_stops_the_check() -> None:
    truncate("event_reviews")

    output = failures()

    assert "event_reviews" in output
    assert "truncate" in output.lower()


def test_accepting_writes_a_row_and_the_check_passes_again() -> None:
    truncate("event_reviews")
    noticed = truncate_rows("event_reviews")
    mark = audit_mark()

    output = accept("staging reset with practice data")

    assert "These were truncated: event_reviews (" in output
    assert "sql as cucumber_owner" in output
    assert "Accepted. The deploy will go on." in output
    [row] = audit_rows_since(mark)
    assert (row.action, row.table_name, row.actor_id) == (
        "guards_accepted",
        "audit_log",
        system_id(),
    )
    assert row.note == "staging reset with practice data"
    assert (row.via, row.db_user) == ("cucumber_check_guards", "cucumber_owner")
    assert row.after == {"truncate_rows": noticed}
    assert "protections on." in check()


@pytest.mark.parametrize("note", ["", "   "])
def test_accepting_needs_a_reason(note: str) -> None:
    truncate("event_reviews")
    mark = audit_mark()

    with pytest.raises(CommandError):
        accept(note)

    assert audit_rows_since(mark) == []


def test_with_nothing_to_accept_nothing_is_written() -> None:
    mark = audit_mark()

    output = accept("just checking")

    assert "Nothing to accept." in output
    assert audit_rows_since(mark) == []


@pytest.mark.django_db(transaction=True)
def test_an_acceptance_written_by_the_app_user_doesnt_count(
    app_db: AppConnection,
) -> None:
    """Review M3: only the owner's acceptance silences the alarm (§5.4)."""
    restore_audit_rows()
    accept_noticed_truncates()
    run("TRUNCATE event_reviews")
    noticed = truncate_rows("event_reviews")

    app_db.execute(
        b"INSERT INTO audit_log"
        b" (actor_id, table_name, row_pk, action, after, note, via)"
        b" VALUES (%s, 'audit_log', '', 'guards_accepted',"
        b" jsonb_build_object('truncate_rows', %s::bigint[]), 'not me', 'app')",
        [system_id(), noticed],
    )

    assert "event_reviews" in failures()
