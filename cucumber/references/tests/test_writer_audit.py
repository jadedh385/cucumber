"""AC19–AC21: every change writes one audit row, field by field (design §6).

A refused change writes none. `require` and `audited` are replaced by spies
to show the order the writers use them in (AC20).
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from django.contrib.auth.models import User
from django.db import transaction

from cucumber.accounts import permissions
from cucumber.accounts.permissions import NotAllowed
from cucumber.core import audit
from cucumber.core.audit import VIA_APP, Reason
from cucumber.core.refusals import Refused
from cucumber.core.tests.rows import db_now, refused_by, update
from cucumber.core.tests.trail import (
    NO_LONGER_USED,
    AuditRow,
    audit_mark,
    audit_rows_since,
    only_row,
)
from cucumber.references import services
from cucumber.references.lists import ListName
from cucumber.references.reading import item
from cucumber.references.services import add_item, edit_label, switch_off, switch_on
from cucumber.references.tests.support import (
    ADDABLE,
    SEEDED,
    SWITCHABLE,
    label_column,
    nothing_written,
    switched_off,
)

pytestmark = pytest.mark.django_db

M = ListName.MEDIA_CODES
SHELL_VIA = "manage.py shell by jade (no ssh connection)"
WRITERS = ["add_item", "edit_label", "switch_off", "switch_on"]


def only_audit_row(mark: int, name: ListName) -> AuditRow:
    """The one audit row of the change, and no other row at all."""
    assert len(audit_rows_since(mark)) == 1, audit_rows_since(mark)
    return only_row(mark, name.value)


# ------------------------------------------------------------------ add_item


@pytest.mark.parametrize(("name", "code"), ADDABLE.items())
def test_an_add_writes_one_insert_row_with_the_whole_new_row(
    admin: User, name: ListName, code: str
) -> None:
    mark = audit_mark()

    add_item(admin, name, code, "New thing")

    row = only_audit_row(mark, name)
    assert (row.table_name, row.row_pk, row.action) == (name.value, code, "insert")
    assert row.before is None
    assert row.after is not None
    wanted = {"code": code, label_column(name): "New thing", "active": True}
    assert wanted.items() <= row.after.items()
    assert (row.reason_code, row.note) == (None, None)


# ---------------------------------------------------------------- edit_label


@pytest.mark.parametrize(("name", "code"), SEEDED.items())
def test_a_label_edit_writes_one_update_row_with_the_old_and_new_label(
    admin: User, name: ListName, code: str
) -> None:
    old = item(name, code)
    assert old is not None
    mark = audit_mark()

    edit_label(admin, name, code, "A better word")

    row = only_audit_row(mark, name)
    column = label_column(name)
    assert (row.table_name, row.row_pk, row.action) == (name.value, code, "update")
    assert row.before == {column: old.label}
    assert row.after == {column: "A better word"}
    assert (row.reason_code, row.note) == (None, None)


# --------------------------------------------------------------- switch_off


@pytest.mark.parametrize("name", SWITCHABLE)
def test_a_switch_off_writes_one_update_row_with_the_reason_and_trimmed_note(
    admin: User, name: ListName
) -> None:
    mark = audit_mark()

    switch_off(admin, name, SEEDED[name], Reason(NO_LONGER_USED, "  old recipe \n"))

    row = only_audit_row(mark, name)
    assert (row.table_name, row.row_pk, row.action) == (
        name.value,
        SEEDED[name],
        "update",
    )
    assert (row.before, row.after) == ({"active": True}, {"active": False})
    assert (row.reason_code, row.note) == (NO_LONGER_USED, "old recipe")


def test_a_switch_off_with_no_note_records_no_note(admin: User) -> None:
    mark = audit_mark()

    switch_off(admin, M, "M001", Reason(NO_LONGER_USED))

    assert not only_audit_row(mark, M).note


# ---------------------------------------------------------------- switch_on


@pytest.mark.parametrize("name", SWITCHABLE)
def test_a_switch_on_writes_one_update_row_with_no_reason(
    admin: User, name: ListName
) -> None:
    switched_off(name, SEEDED[name])
    mark = audit_mark()

    switch_on(admin, name, SEEDED[name])

    row = only_audit_row(mark, name)
    assert (row.table_name, row.row_pk, row.action) == (
        name.value,
        SEEDED[name],
        "update",
    )
    assert (row.before, row.after) == ({"active": False}, {"active": True})
    assert (row.reason_code, row.note) == (None, None)


# ------------------------------------------------------ who, when, via, db_user


def each_change(who: User) -> dict[str, Callable[..., object]]:
    """One change per writer on media codes, `who` making it."""
    switched_off(M, "M004")
    return {
        "add_item": lambda **kw: add_item(who, M, "M777", "New", **kw),
        "edit_label": lambda **kw: edit_label(who, M, "M001", "Half MS", **kw),
        "switch_off": lambda **kw: switch_off(
            who, M, "M002", Reason(NO_LONGER_USED), **kw
        ),
        "switch_on": lambda **kw: switch_on(who, M, "M004", **kw),
    }


@pytest.mark.parametrize("writer", WRITERS)
def test_the_row_names_the_signed_in_person_and_the_app(
    admin: User, writer: str
) -> None:
    change = each_change(admin)[writer]
    mark = audit_mark()

    change()

    row = only_audit_row(mark, M)
    assert row.actor_id == admin.pk
    assert row.via == VIA_APP
    assert row.db_user


@pytest.mark.parametrize("writer", WRITERS)
def test_a_shell_session_names_itself_in_via(admin: User, writer: str) -> None:
    change = each_change(admin)[writer]
    mark = audit_mark()

    change(via=SHELL_VIA)

    assert only_audit_row(mark, M).via == SHELL_VIA


@pytest.mark.parametrize("writer", WRITERS)
def test_the_row_is_stamped_by_the_database_clock(admin: User, writer: str) -> None:
    change = each_change(admin)[writer]
    mark = audit_mark()

    change()

    assert only_audit_row(mark, M).at == db_now()


def test_each_change_is_its_own_row_in_order(admin: User) -> None:
    mark = audit_mark()

    add_item(admin, M, "M777", "New")
    edit_label(admin, M, "M777", "Newer")
    switch_off(admin, M, "M777", Reason(NO_LONGER_USED))
    switch_on(admin, M, "M777")

    rows = audit_rows_since(mark, "media_codes")
    assert [row.action for row in rows] == ["insert", "update", "update", "update"]
    assert [row.after for row in rows[1:]] == [
        {"label": "Newer"},
        {"active": False},
        {"active": True},
    ]


# ----------------------------------------------------- AC21: refused, no row


@pytest.mark.parametrize(
    "refused",
    [
        pytest.param(lambda who: add_item(who, M, "m777", "Bad code"), id="bad code"),
        pytest.param(lambda who: add_item(who, M, "M001", "Taken"), id="code taken"),
        pytest.param(lambda who: edit_label(who, M, "M001", ""), id="blank label"),
        pytest.param(lambda who: edit_label(who, M, "M999", "X"), id="unknown"),
        pytest.param(lambda who: switch_off(who, M, "M001", None), id="no reason"),
        pytest.param(
            lambda who: switch_off(who, M, "M001", Reason("void_duplicate_entry")),
            id="void reason",
        ),
        pytest.param(
            lambda who: add_item(who, ListName.STAGES, "S9", "Nine"), id="stage add"
        ),
        pytest.param(
            lambda who: switch_off(
                who, ListName.LOCATIONS, "lab", Reason(NO_LONGER_USED)
            ),
            id="location off",
        ),
        pytest.param(
            lambda who: edit_label(who, ListName.ACTIONS, "intake", "X"),
            id="fixed list",
        ),
    ],
)
def test_a_change_that_breaks_a_rule_saves_nothing_and_writes_no_audit_row(
    admin: User, refused: Callable[[User], object]
) -> None:
    with nothing_written(M), pytest.raises(Refused):
        refused(admin)


@pytest.mark.parametrize("who", ["supervisor", "tech", "read_only", "no_role"])
def test_a_change_by_the_wrong_role_saves_nothing_and_writes_no_audit_row(
    who: str, request: pytest.FixtureRequest
) -> None:
    person: User = request.getfixturevalue(who)

    with nothing_written(M), pytest.raises(NotAllowed):
        edit_label(person, M, "M001", "Half MS")


def test_a_change_by_a_switched_off_account_writes_no_audit_row(
    deactivated_tech: User,
) -> None:
    with nothing_written(M), pytest.raises(NotAllowed):
        switch_on(deactivated_tech, M, "M001")


def test_a_refusal_inside_the_transaction_takes_the_audit_row_with_it(
    admin: User,
) -> None:
    """A rule only the database can check (a genus name taken) fails after
    the writer is inside `audited()`, so the row goes back with it."""
    with nothing_written(ListName.GENERA), pytest.raises(Refused):
        edit_label(admin, ListName.GENERA, "PHL", "Hoya")


# -------------------------------------------- AC19, AC20: no audit, no change


def test_a_change_with_nobody_named_is_refused_by_the_database() -> None:
    with refused_by("audit_actor_required"):
        update("container_types", "magenta_box", {"label": "Box"}, "code")


@contextmanager
def no_person_named(*_: Any, **__: Any) -> Iterator[None]:
    """`audited()` replaced by a plain transaction: nobody is named."""
    with transaction.atomic():
        yield


def test_a_writer_that_skipped_audited_would_save_nothing(
    admin: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(services, "audited", no_person_named, raising=False)

    with nothing_written(M), pytest.raises(Refused) as refused:
        edit_label(admin, M, "M001", "Half MS")

    assert refused.value.rule == "audit_actor_required"


# ---------------------------------------------- AC20: require, audited, save


@pytest.fixture
def order(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """What `require` and `audited` saw, in order, with the real ones working."""
    seen: list[str] = []
    real_require, real_audited = permissions.require, audit.audited

    def spy_require(user: User, permission: permissions.Permission) -> Any:
        seen.append(f"require {permission}")
        return real_require(user, permission)

    @contextmanager
    def spy_audited(*args: Any, **kwargs: Any) -> Iterator[None]:
        seen.append("audited entered")
        with real_audited(*args, **kwargs):
            yield
            seen.append(f"saved with reason {kwargs.get('reason') is not None}")
        seen.append("audited left")

    monkeypatch.setattr(services, "require", spy_require, raising=False)
    monkeypatch.setattr(services, "audited", spy_audited, raising=False)
    return seen


@pytest.mark.parametrize("writer", WRITERS)
def test_a_writer_checks_the_permission_then_opens_audited_then_saves(
    admin: User, order: list[str], writer: str
) -> None:
    change = each_change(admin)[writer]
    mark = audit_mark()

    change()

    assert order[0] == "require edit_reference_lists"
    assert order[1] == "audited entered"
    assert order[-1] == "audited left"
    assert len(order) == 4
    assert len(audit_rows_since(mark)) == 1


def test_audited_is_given_a_reason_for_a_switch_off_and_none_for_a_switch_on(
    admin: User, order: list[str]
) -> None:
    switch_off(admin, M, "M001", Reason(NO_LONGER_USED))
    switch_on(admin, M, "M001")

    assert [line for line in order if line.startswith("saved")] == [
        "saved with reason True",
        "saved with reason False",
    ]


@pytest.mark.parametrize("writer", WRITERS)
def test_a_refused_person_never_gets_as_far_as_audited(
    tech: User, order: list[str], writer: str
) -> None:
    change = each_change(tech)[writer]
    order.clear()  # set-up above may have used the spies

    with pytest.raises(NotAllowed):
        change()

    assert order == ["require edit_reference_lists"]


@pytest.mark.parametrize(
    ("call", "rule"),
    [
        (lambda who: edit_label(who, ListName.ACTIONS, "intake", "X"), "list_fixed"),
        (lambda who: add_item(who, M, "m777", "X"), "media_codes_code_format"),
        (lambda who: switch_off(who, M, "M001", None), "reason_required"),
    ],
)
def test_a_rule_checked_before_the_save_never_gets_as_far_as_audited(
    admin: User, order: list[str], call: Callable[[User], object], rule: str
) -> None:
    with pytest.raises(Refused) as refused:
        call(admin)

    assert refused.value.rule == rule
    assert order == ["require edit_reference_lists"]
