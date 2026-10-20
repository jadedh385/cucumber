"""AC4–AC6: `audited()` names the person for the database (design §3).

It opens a transaction, sets the `cucumber.*` settings for it, and puts back
what was there before on the way out (review H1). System is looked up again
on every call (review H2).
"""

import pytest
from django.contrib.auth.models import User

from cucumber.core.audit import (
    LONGEST_NOTE,
    SYSTEM,
    SYSTEM_USERNAME,
    Reason,
    audited,
    system_account,
)
from cucumber.core.tests.rows import refused_by, run, update
from cucumber.core.tests.stock import make_staff, refused
from cucumber.core.tests.trail import (
    LEFT_COMPANY,
    VIA_TEST,
    as_system,
    audit_mark,
    audit_rows_since,
    only_row,
    restore_audit_rows,
    setting,
    system_id,
)

pytestmark = pytest.mark.django_db

ALL_SETTINGS = ("actor_id", "via", "reason_code", "note")


@pytest.fixture
def gene() -> User:
    with as_system():
        return make_staff("gene", "tech")


@pytest.fixture
def jade() -> User:
    with as_system():
        return make_staff("jade", "admin")


# ------------------------------------------------------------ the settings
def test_inside_audited_the_person_and_how_are_named(jade: User) -> None:
    with audited(jade):
        assert setting("actor_id") == str(jade.pk)
        assert setting("via") == "app"
        assert setting("reason_code") == ""
        assert setting("note") == ""


def test_a_reason_is_named_too_with_its_note_trimmed(jade: User) -> None:
    reason = Reason(LEFT_COMPANY, "  moved to Chiang Mai \n")

    with audited(jade, via="cucumber_admin", reason=reason):
        assert setting("via") == "cucumber_admin"
        assert setting("reason_code") == LEFT_COMPANY
        assert setting("note") == "moved to Chiang Mai"


def test_a_note_of_500_characters_is_fine(jade: User) -> None:
    with audited(jade, reason=Reason(LEFT_COMPANY, "x" * LONGEST_NOTE)):
        assert len(setting("note")) == LONGEST_NOTE


def test_a_longer_note_is_refused_before_anything_starts(jade: User) -> None:
    long_note = Reason(LEFT_COMPANY, "x" * (LONGEST_NOTE + 1))

    with refused("reason_note_too_long"), audited(jade, reason=long_note):
        pytest.fail("the block must not run")


def test_the_settings_are_put_back_on_the_way_out(jade: User) -> None:
    """Review H1: inside the test's transaction, atomic() is only a savepoint."""
    with audited(jade, reason=Reason(LEFT_COMPANY, "note")):
        pass

    assert [setting(name) for name in ALL_SETTINGS] == ["", "", "", ""]


def test_the_settings_are_put_back_after_an_error_too(jade: User) -> None:
    with pytest.raises(ValueError, match="boom"), audited(jade):
        raise ValueError("boom")

    assert [setting(name) for name in ALL_SETTINGS] == ["", "", "", ""]


def test_the_outer_person_comes_back_after_an_inner_block(jade: User) -> None:
    with audited(jade):
        with audited(jade, via="cucumber_flag"):
            assert setting("via") == "cucumber_flag"
        assert setting("actor_id") == str(jade.pk)
        assert setting("via") == "app"


def test_nesting_for_a_different_person_is_a_programming_error(
    jade: User, gene: User
) -> None:
    with pytest.raises(RuntimeError), audited(jade), audited(gene):
        pass


def test_an_error_inside_undoes_the_writes(jade: User, gene: User) -> None:
    with pytest.raises(ValueError, match="boom"), audited(jade):
        update("auth_user", gene.pk, {"is_staff": True})
        raise ValueError("boom")

    assert User.objects.get(pk=gene.pk).is_staff is False


# ------------------------------------------------------------------- System
def test_the_system_account_is_reserved_and_switched_off() -> None:
    """Design §5.2, AC6."""
    system = system_account()

    assert system.username == SYSTEM_USERNAME
    assert system.email == SYSTEM_USERNAME
    assert system.first_name == "System"
    assert system.is_active is False
    assert system.has_usable_password() is False
    assert list(system.groups.all()) == []


def test_system_names_the_system_account() -> None:
    with audited(SYSTEM, via="cucumber_flag"):
        assert setting("actor_id") == str(system_id())


def test_a_change_made_as_system_names_it_in_the_trail(gene: User) -> None:
    mark = audit_mark()

    with audited(SYSTEM, via="cucumber_admin"):
        update("auth_user", gene.pk, {"is_staff": True})

    row = only_row(mark, "auth_user")
    assert (row.actor_id, row.via) == (system_id(), "cucumber_admin")


# --------------------------------------------- a forgetful caller (review H1)
def test_after_a_builder_a_write_without_audited_is_still_refused(
    gene: User,
) -> None:
    """The builder's System must not stay named for the rest of the test."""
    with as_system():
        make_staff("pim", "tech")

    with refused_by("audit_actor_required"):
        update("auth_user", gene.pk, {"is_staff": True})


def test_set_up_rows_are_marked_as_the_tests_own() -> None:
    mark = audit_mark()

    with as_system():
        make_staff("pim", "tech")

    assert {row.via for row in audit_rows_since(mark)} == {VIA_TEST}


# ----------------------------------------------- after a flush (review H2)
@pytest.mark.django_db(transaction=True)
def test_system_is_looked_up_again_after_the_database_is_emptied() -> None:
    """A committing test empties the database; System comes back with a new id."""
    restore_audit_rows()
    first = system_id()
    run("ALTER TABLE auth_user DISABLE TRIGGER USER")
    run(
        "UPDATE auth_user SET username = 'old-system@cucumber.invalid'"
        " WHERE username = %s",
        [SYSTEM_USERNAME],
    )
    run("ALTER TABLE auth_user ENABLE TRIGGER USER")
    restore_audit_rows()

    with audited(SYSTEM, via="cucumber_flag"):
        assert setting("actor_id") == str(system_id())
    assert system_id() != first
