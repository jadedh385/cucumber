"""AC15: `cucumber_check_guards` notices a protection switched off (design §8).

Each kind in §8.1 is broken one at a time inside the test's transaction,
which puts it back afterwards. Two kinds can't be broken here: making the
app role a superuser or giving it a role setting needs CREATEROLE, which the
tests' login (the owner) doesn't have, just as on the servers.
"""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from cucumber.core import expected, guards
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
    """What the error says when something is off.

    The lines are in the error, not on stdout: the deploy shows a failed
    command's stderr, and stdout is dropped (G4 review, item 5).
    """
    out = StringIO()
    with pytest.raises(CommandError) as raised:
        call_command("cucumber_check_guards", stdout=out)
    assert out.getvalue() == ""
    return str(raised.value)


def accept(note: str, *options: str) -> str:
    out = StringIO()
    call_command("cucumber_check_guards", "--accept", note, *options, stdout=out)
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
    "trigger calls a same-named function in another schema": (
        "CREATE SCHEMA elsewhere;"
        " CREATE FUNCTION elsewhere.cucumber_audit() RETURNS trigger"
        " LANGUAGE plpgsql AS $$ BEGIN RETURN NULL; END $$;"
        " DROP TRIGGER plants_audit ON plants;"
        " CREATE TRIGGER plants_audit AFTER INSERT OR UPDATE ON plants"
        " FOR EACH ROW EXECUTE FUNCTION elsewhere.cucumber_audit('id', 'name_key', '')",
        "plants_audit",
    ),
    "trigger given a WHEN": (
        "DROP TRIGGER plants_audit ON plants;"
        " CREATE TRIGGER plants_audit AFTER INSERT OR UPDATE ON plants"
        " FOR EACH ROW WHEN (false)"
        " EXECUTE FUNCTION cucumber_audit('id', 'name_key', '')",
        "plants_audit",
    ),
    "trigger limited to some columns": (
        "DROP TRIGGER plants_audit ON plants;"
        " CREATE TRIGGER plants_audit AFTER INSERT OR UPDATE OF notes ON plants"
        " FOR EACH ROW EXECUTE FUNCTION cucumber_audit('id', 'name_key', '')",
        "plants_audit",
    ),
    "trigger made deferrable": (
        "DROP TRIGGER plants_audit ON plants;"
        " CREATE CONSTRAINT TRIGGER plants_audit AFTER INSERT OR UPDATE ON plants"
        " DEFERRABLE INITIALLY DEFERRED"
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

    output = accept("staging reset with practice data", "--yes")

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
    assert row.via.startswith("cucumber_check_guards by ")
    assert row.db_user == "cucumber_owner"
    assert row.after == {"truncate_rows": noticed}
    assert "protections on." in check()


@pytest.mark.parametrize("note", ["", "   "])
def test_accepting_needs_a_reason(note: str) -> None:
    truncate("event_reviews")
    mark = audit_mark()

    with pytest.raises(CommandError):
        accept(note, "--yes")

    assert audit_rows_since(mark) == []


def test_with_nothing_to_accept_nothing_is_written() -> None:
    mark = audit_mark()

    output = accept("just checking", "--yes")

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


# ------------------------------------------- the app role's attributes (§8.1)
ROLE_ATTRIBUTES = {
    "createrole": "may create roles",
    "bypassrls": "bypasses row security",
    "replication": "may start replication",
}


@pytest.mark.parametrize("attribute", sorted(ROLE_ATTRIBUTES))
def test_an_app_role_attribute_that_gets_round_the_triggers_is_reported(
    attribute: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The tests' login can't change `cucumber_app`, so a role that has it."""
    row = fetch_all(f"SELECT rolname FROM pg_roles WHERE rol{attribute} LIMIT 1")  # noqa: S608
    if not row:
        pytest.skip(f"no role with {attribute} in this database")
    monkeypatch.setattr(expected, "APP_ROLE", str(row[0][0]))

    output = failures()

    assert ROLE_ATTRIBUTES[attribute] in output


# ------------------------------------- a migration that is missing (review #1)
def test_a_missing_migration_with_later_ones_applied_is_a_failure() -> None:
    """A deleted `django_migrations` row would skip that migration's guards."""
    run("DELETE FROM django_migrations WHERE app = 'core' AND name = '0003_app_grants'")

    output = failures()

    assert "core.0003_app_grants" in output
    assert "not recorded as applied" in output


def test_a_migration_not_yet_run_is_not_a_failure() -> None:
    """Step 3b checks the old database with the new code: that is expected.

    The newest guard migration is the one not yet run; nothing comes after it.
    """
    app, name = expected.U08.split(".", 1)
    run("DELETE FROM django_migrations WHERE app = %s AND name = %s", [app, name])

    assert "protections on." in check()


# ----------------------------------- --accept: ids, lock, confirm, owner (#2)
def test_accepting_lists_what_it_will_accept_and_asks_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truncate("event_reviews")
    mark = audit_mark()
    monkeypatch.setattr("builtins.input", lambda prompt="": "no")

    output = accept("staging reset")

    assert "event_reviews" in output
    assert "Nothing accepted." in output
    assert audit_rows_since(mark) == []
    assert "event_reviews" in failures()


def test_accepting_after_yes_writes_the_row(monkeypatch: pytest.MonkeyPatch) -> None:
    truncate("event_reviews")
    mark = audit_mark()
    monkeypatch.setattr("builtins.input", lambda prompt="": "yes")

    output = accept("staging reset")

    assert "Accepted. The deploy will go on." in output
    assert [row.action for row in audit_rows_since(mark)] == ["guards_accepted"]


def test_no_keyboard_counts_as_no(monkeypatch: pytest.MonkeyPatch) -> None:
    truncate("event_reviews")

    def no_keyboard(prompt: str = "") -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", no_keyboard)

    assert "Nothing accepted." in accept("staging reset")


def test_only_the_listed_truncates_are_accepted() -> None:
    truncate("event_reviews")
    [listed] = truncate_rows("event_reviews")
    truncate("plant_status_changes")

    guards.accept_truncates("only the first", [listed])

    output = failures()
    assert "plant_status_changes" in output
    assert "event_reviews" not in output


def test_a_truncate_after_the_listing_is_still_noticed() -> None:
    truncate("event_reviews")
    listed = [row_id for row_id, _, _ in guards.noticed_truncates()]
    truncate("plant_status_changes")

    guards.accept_truncates("what I saw", listed)

    assert "plant_status_changes" in failures()


def test_accepting_takes_a_lock_on_the_trail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A truncate can't slip in between the listing and the acceptance."""
    truncate("event_reviews")
    locked: list[bool] = []
    monkeypatch.setattr(guards, "lock_trail", lambda: locked.append(True))

    guards.accept_truncates(
        "why", [row_id for row_id, _, _ in guards.noticed_truncates()]
    )

    assert locked == [True]


def test_accepting_is_refused_unless_the_session_user_is_the_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    truncate("event_reviews")
    mark = audit_mark()
    monkeypatch.setattr(guards, "session_user", lambda: "cucumber_app")

    with pytest.raises(CommandError, match="database owner"):
        accept("staging reset", "--yes")

    assert audit_rows_since(mark) == []


# ------------------------------------------ the SSH user and connection (#3)
def test_an_acceptance_names_the_ssh_user_and_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SSH_USER", "sawat")
    monkeypatch.setenv("SSH_CONNECTION", "203.0.113.5 52211 10.0.0.2 22")
    truncate("event_reviews")
    mark = audit_mark()

    accept("staging reset", "--yes")

    [row] = audit_rows_since(mark)
    assert row.via == (
        "cucumber_check_guards by sawat (ssh 203.0.113.5 52211 10.0.0.2 22)"
    )
