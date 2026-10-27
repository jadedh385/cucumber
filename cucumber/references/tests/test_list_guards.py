"""U0.9 design §2.3: `cucumber_check_guards` knows the new protections.

`references 0007` adds seven triggers (five on `container_types`, built from
the existing helpers, and the two owner-only ones), the `cucumber_owner_only`
function and the `container_types` grant. `expected.py` lists each with the
migration that makes it (`expected.U09`), so a fresh database passes and each
one is reported when it is dropped or changed.

The breaks only exist once `0007` has run, so those tests say so first:
before G3 they fail on the missing migration, not on a statement PostgreSQL
refuses (as U0.8's generator tests do).
"""

import hashlib

import pytest

from cucumber.core import db_rules, expected, guards
from cucumber.core.expected import BEFORE_INSERT_OR_UPDATE, FIXED_SEARCH_PATH
from cucumber.core.guards import GUARDS, Kind
from cucumber.core.tests.rows import run
from cucumber.core.tests.test_check_guards import check, failures
from cucumber.core.tests.trail import accept_noticed_truncates

pytestmark = pytest.mark.django_db

OWNER_ONLY = "cucumber_owner_only"
CONTAINER_TYPE_TRIGGERS = {
    f"container_types_{rule}": "container_types"
    for rule in [
        "no_delete", "code_rename", "audit", "reason_required", "truncate_noticed",
    ]
}  # fmt: skip
OWNER_ONLY_TRIGGERS = {
    "stages_order_fixed": ("stages", ("stages_order_fixed", "sort_order")),
    "locations_fixed": ("locations", ("locations_fixed", "active")),
}
U09_TRIGGERS = {
    **CONTAINER_TYPE_TRIGGERS,
    **{name: table for name, (table, _) in OWNER_ONLY_TRIGGERS.items()},
}


@pytest.fixture(autouse=True)
def earlier_flushes_accepted() -> None:
    """A committing test's flush leaves `truncate` rows; they aren't this test's."""
    accept_noticed_truncates()


@pytest.fixture
def u09_has_run() -> None:
    """These breaks need `references 0007`'s triggers and function (design §2.3)."""
    assert expected.U09 in guards.applied_migrations(), (
        f"{expected.U09} hasn't run: no container_types table, owner-only"
        " triggers or cucumber_owner_only() yet (U0.9 G3)"
    )


def lines(output: str) -> list[str]:
    return [line.strip() for line in output.splitlines() if line.strip()]


# ------------------------------------------------------- what is expected
def test_each_new_trigger_is_expected_from_references_0007() -> None:
    found = {
        name: migration
        for name, (_, migration) in expected.TRIGGERS.items()
        if name in U09_TRIGGERS
    }

    assert found == dict.fromkeys(U09_TRIGGERS, expected.U09)


@pytest.mark.parametrize("name", sorted(OWNER_ONLY_TRIGGERS))
def test_an_owner_only_trigger_takes_its_rule_then_its_columns(name: str) -> None:
    table, arguments = OWNER_ONLY_TRIGGERS[name]

    assert expected.TRIGGERS.get(name) == (
        expected.Trigger(table, OWNER_ONLY, BEFORE_INSERT_OR_UPDATE, arguments),
        expected.U09,
    )


@pytest.mark.parametrize(
    "rule", ["no_delete", "code_rename", "audit", "reason_required", "truncate_noticed"]
)
def test_a_container_type_trigger_is_built_like_the_other_lists(rule: str) -> None:
    """The same function, timing and arguments as `media_codes`'s (design §2.3)."""
    container = expected.TRIGGERS.get(f"container_types_{rule}")
    media, _ = expected.TRIGGERS[f"media_codes_{rule}"]

    assert container is not None, f"container_types_{rule} isn't expected"
    assert (container[0].function, container[0].tgtype, container[0].arguments) == (
        media.function,
        media.tgtype,
        media.arguments,
    )


def test_the_owner_only_function_is_pinned_by_its_body() -> None:
    """In `U09_FUNCTIONS`, not the lists core 0006 and 0007 loop over (L3)."""
    bodies = getattr(db_rules, "U09_FUNCTIONS", {})
    assert OWNER_ONLY in bodies, "db_rules.U09_FUNCTIONS has no cucumber_owner_only"
    md5 = hashlib.md5(bodies[OWNER_ONLY].encode(), usedforsecurity=False).hexdigest()

    assert expected.FUNCTIONS.get(OWNER_ONLY) == (
        expected.Function(md5, FIXED_SEARCH_PATH),
        expected.U09,
    )
    assert OWNER_ONLY not in db_rules.AUDIT_FUNCTIONS
    assert OWNER_ONLY not in db_rules.ID_FUNCTIONS


def test_the_app_may_add_and_change_container_types_but_not_delete_them() -> None:
    """An explicit grant, not the default privileges (U0.8 review L2)."""
    assert expected.PRIVILEGES.get("container_types") == (
        expected.ADD_CHANGE,
        expected.U09,
    )


def test_the_guard_check_holds_the_nine_new_protections() -> None:
    """Seven triggers, one function, one grant (design §2.3, "about 9")."""
    found = {
        (guard.kind, guard.name) for guard in GUARDS if guard.migration == expected.U09
    }

    assert found == {
        *((Kind.TRIGGER, name) for name in U09_TRIGGERS),
        (Kind.FUNCTION, OWNER_ONLY),
        (Kind.GRANT, "container_types"),
    }


# --------------------------------------------------------- a fresh database
@pytest.mark.usefixtures("u09_has_run")
def test_a_fresh_database_passes_with_the_new_protections() -> None:
    report = guards.check()

    assert report.failures == ()
    assert report.checked == len(GUARDS)
    assert "protections on." in check()


# --------------------------------------------------- broken one at a time
@pytest.mark.usefixtures("u09_has_run")
@pytest.mark.parametrize("name", sorted(U09_TRIGGERS))
def test_a_new_trigger_dropped_is_reported(name: str) -> None:
    table = U09_TRIGGERS[name]
    run(f"DROP TRIGGER {name} ON {table}")

    assert f"trigger {name} on {table} is missing" in lines(failures())


@pytest.mark.usefixtures("u09_has_run")
@pytest.mark.parametrize("name", sorted(OWNER_ONLY_TRIGGERS))
def test_an_owner_only_trigger_disabled_is_reported(name: str) -> None:
    table, _ = OWNER_ONLY_TRIGGERS[name]
    run(f"ALTER TABLE {table} DISABLE TRIGGER {name}")

    assert f"trigger {name} on {table} is disabled" in lines(failures())


@pytest.mark.usefixtures("u09_has_run")
def test_an_owner_only_trigger_that_no_longer_names_its_column_is_reported() -> None:
    run(
        "DROP TRIGGER stages_order_fixed ON stages;"
        " CREATE TRIGGER stages_order_fixed BEFORE INSERT OR UPDATE ON stages"
        " FOR EACH ROW EXECUTE FUNCTION cucumber_owner_only('stages_order_fixed')"
    )

    assert (
        "trigger stages_order_fixed on stages has changed arguments:"
        " ('stages_order_fixed',)"
    ) in lines(failures())


@pytest.mark.usefixtures("u09_has_run")
def test_an_owner_only_trigger_on_insert_only_is_reported() -> None:
    """Without UPDATE, a location could be switched off (AC9)."""
    run(
        "DROP TRIGGER locations_fixed ON locations;"
        " CREATE TRIGGER locations_fixed BEFORE INSERT ON locations FOR EACH ROW"
        " EXECUTE FUNCTION cucumber_owner_only('locations_fixed', 'active')"
    )

    assert (
        "trigger locations_fixed on locations fires on the wrong table or at the"
        " wrong time"
    ) in lines(failures())


@pytest.mark.usefixtures("u09_has_run")
def test_the_owner_only_function_changed_is_reported() -> None:
    run(
        "CREATE OR REPLACE FUNCTION cucumber_owner_only() RETURNS trigger"
        " LANGUAGE plpgsql SET search_path = pg_catalog, public, pg_temp"
        " AS $$ BEGIN RETURN NEW; END $$"
    )

    assert f"function {OWNER_ONLY}() has a changed body" in lines(failures())


@pytest.mark.usefixtures("u09_has_run")
def test_the_owner_only_function_dropped_is_reported() -> None:
    run(f"DROP FUNCTION {OWNER_ONLY}() CASCADE")  # its two triggers go with it

    found = lines(failures())

    assert f"function {OWNER_ONLY}() is missing" in found
    assert "trigger stages_order_fixed on stages is missing" in found
    assert "trigger locations_fixed on locations is missing" in found


@pytest.mark.usefixtures("u09_has_run")
@pytest.mark.parametrize(
    ("statement", "problem"),
    [
        (
            f"ALTER FUNCTION {OWNER_ONLY}() SECURITY DEFINER",
            f"function {OWNER_ONLY}() runs as its owner (SECURITY DEFINER)",
        ),
        (
            f"ALTER FUNCTION {OWNER_ONLY}() RESET search_path",
            f"function {OWNER_ONLY}() has changed settings: ()",
        ),
    ],
    ids=["security definer", "search_path removed"],
)
def test_the_owner_only_function_s_settings_changed_are_reported(
    statement: str, problem: str
) -> None:
    run(statement)

    assert problem in lines(failures())


# -------------------------------------------------------------- the grant
@pytest.mark.usefixtures("u09_has_run")
@pytest.mark.parametrize(
    ("statement", "now"),
    [
        (
            "GRANT DELETE ON container_types TO cucumber_app",
            "DELETE, INSERT, SELECT, UPDATE",
        ),
        ("REVOKE UPDATE ON container_types FROM cucumber_app", "INSERT, SELECT"),
    ],
    ids=["delete granted", "update revoked"],
)
def test_a_container_types_grant_changed_is_reported(statement: str, now: str) -> None:
    run(statement)

    assert (
        f"table container_types: cucumber_app may {now}, should be INSERT, SELECT,"
        " UPDATE"
    ) in lines(failures())
