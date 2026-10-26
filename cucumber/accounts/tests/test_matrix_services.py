"""AC12, AC14: every service row of the matrix, tried by every kind of person.

Generated from `MATRIX` (design §10.1): for each row checked in the services,
`PROBES` holds one small action on stock data, and each person tries it. The
expected answer comes from the row's cells: "saved", or the refusal's rule
with nothing written. Narrowing rules (Undo window, N7, not your own) have
their own tests in events/tests/test_event_permissions.py.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass

import pytest
from django.contrib.auth.models import User

from cucumber.accounts.permissions import (
    MATRIX,
    Built,
    NotAllowed,
    Permission,
    Role,
    Row,
)
from cucumber.accounts.services import (
    add_account,
    deactivate,
    give_new_password,
    lift_lock,
    reactivate,
    set_role,
)
from cucumber.core.audit import Reason
from cucumber.core.refusals import Refused
from cucumber.core.tests.rows import as_int, fetch_one, insert, make_event
from cucumber.core.tests.stock import intake_into_new_batch, log, make_staff
from cucumber.core.tests.trail import LEFT_THE_COMPANY, NO_LONGER_USED, as_system
from cucumber.events.models import Event
from cucumber.events.reviews import review
from cucumber.events.services import close, correct, split, void
from cucumber.ids.issuing import issue_next_sku
from cucumber.plants.services import reclassify_genus
from cucumber.references.lists import ListName
from cucumber.references.services import add_item, edit_label, switch_off, switch_on

pytestmark = pytest.mark.django_db

SAVED = "saved"
ROWS = {row.permission: row for row in MATRIX}
SERVICE_ROWS = [row for row in MATRIX if row.built in {Built.SERVICES, Built.BOTH}]
OTHER_TECH = "tech_9@example.com"


@dataclass(frozen=True)
class Person:
    fixture: str
    role: Role | None
    is_active: bool = True


PEOPLE = [
    Person("admin", Role.ADMIN),
    Person("supervisor", Role.SUPERVISOR),
    Person("tech", Role.TECH),
    Person("read_only", Role.READ_ONLY),
    Person("no_role", None),
    Person("deactivated_tech", Role.TECH, is_active=False),
]


@dataclass(frozen=True)
class Stock:
    """What the probes act on, none of it done or saved by the person trying."""

    plant: int
    batch: int  # a Nursery batch of 10 the Admin took in
    others_entry: int  # an `out` another Tech did and saved
    others_void: uuid.UUID  # the operation of that Tech's Undo of their own entry


@pytest.fixture
def stock(plant: int, admin: User) -> Stock:
    other = make_staff("tech_9", "tech")
    with as_system():
        insert("genera", {"code": "ANT", "name": "Anthurium", "active": True}, "code")
    batch = intake_into_new_batch(admin, plant, 10)
    others_entry = log(other, batch, "out", qty_out=1)
    undone = log(other, batch, "out", qty_out=1)
    others_void = void(other, undone, "void_wrong_batch").operation_id
    return Stock(plant, batch, others_entry, others_void)


def operation_of(event_id: int) -> uuid.UUID:
    return Event.objects.get(pk=event_id).operation_id


def nothing_to_prepare(who: User, stock: Stock) -> int:
    return 0


def own_entry(who: User, stock: Stock) -> int:
    """An entry `who` did and saved just now, written straight into the table,
    so a person who may not save still has one to try to undo."""
    return make_event(stock.batch, who.pk, "out", qty_out=1)


@dataclass(frozen=True)
class Probe:
    """One try at a row's action. `prepare` runs first (its writes don't
    count) and hands `run` an event id; `needs` are rows the action also
    needs, checked first."""

    run: Callable[[User, Stock, int], object]
    needs: tuple[Permission, ...] = ()
    prepare: Callable[[User, Stock], int] = nothing_to_prepare


def entered_for_another(who: User, stock: Stock, _: int) -> object:
    other = User.objects.get(username=OTHER_TECH)
    return log(who, stock.batch, "count", counted_qty=8, staff_id=other.pk)


PROBES: dict[Permission, Probe] = {
    Permission.LOG_WORK: Probe(
        lambda who, s, _: log(who, s.batch, "count", counted_qty=8)
    ),
    Permission.SPLIT_CLOSE_LOSS: Probe(
        lambda who, s, _: log(who, s.batch, "loss", qty_out=1, reason_code="loss_rot")
    ),
    Permission.RELEASE_QUARANTINE: Probe(
        lambda who, s, _: log(who, s.batch, "release")
    ),
    Permission.UNDO_OWN: Probe(
        lambda who, s, entry: void(who, entry, "void_wrong_batch"),
        prepare=own_entry,
    ),
    Permission.REVIEW_EVENTS: Probe(
        lambda who, s, _: review(who, operation_of(s.others_entry))
    ),
    # A Correction, so a Tech meets the role and not the Void tree (§10.1).
    Permission.VOID_OR_CORRECT: Probe(
        lambda who, s, _: correct(
            who, s.others_entry, "correction_wrong_quantity", qty_out=2
        )
    ),
    Permission.REVIEW_VOIDS: Probe(
        lambda who, s, _: review(who, s.others_void),
        needs=(Permission.REVIEW_EVENTS,),
    ),
    Permission.ENTER_FOR_OTHERS: Probe(
        entered_for_another, needs=(Permission.LOG_WORK,)
    ),
    Permission.PLANT_LIFECYCLE: Probe(
        lambda who, s, _: issue_next_sku(s.plant, "PHL", who)
    ),
    Permission.RECLASSIFY_GENUS: Probe(
        lambda who, s, _: reclassify_genus(who, s.plant, "ANT")
    ),
    Permission.MANAGE_USERS: Probe(
        lambda who, s, _: add_account(who, "Mali", "mali@example.com", Role.TECH)
    ),
    # A label edit adds a row to no table but the trail (U0.9 design §5).
    Permission.EDIT_REFERENCE_LISTS: Probe(
        lambda who, s, _: edit_label(who, ListName.MEDIA_CODES, "M001", "Half MS")
    ),
}

WRITTEN_TABLES = [
    "operations",
    "events",
    "event_reviews",
    "batches",
    "plants",
    "skus",
    "plant_status_changes",
    "auth_user",
    "auth_user_groups",
    "audit_log",  # U0.9: a reference list edit writes only its audit row
]


def written() -> dict[str, int]:
    return {
        table: as_int(fetch_one(f"SELECT count(*) FROM {table}")[0])  # noqa: S608
        for table in WRITTEN_TABLES
    }


def expected(row: Row, probe: Probe, person: Person) -> str:
    """The answer the matrix gives this person for this row."""
    if not person.is_active:
        return "account_not_active"
    for needed in (*probe.needs, row.permission):
        if person.role not in ROWS[needed].allowed:
            return ROWS[needed].refused_as
    return SAVED


def outcome(probe: Probe, who: User, stock: Stock, prepared: int) -> str:
    try:
        probe.run(who, stock, prepared)
    except NotAllowed as refusal:
        return refusal.rule
    except Refused as refusal:
        return refusal.rule
    return SAVED


def test_every_service_row_has_a_probe() -> None:
    assert set(PROBES) == {row.permission for row in SERVICE_ROWS}


@pytest.mark.parametrize("person", PEOPLE, ids=lambda person: person.fixture)
@pytest.mark.parametrize("row", SERVICE_ROWS, ids=lambda row: str(row.permission))
def test_each_person_may_do_exactly_what_their_row_allows(
    row: Row, person: Person, stock: Stock, request: pytest.FixtureRequest
) -> None:
    who: User = request.getfixturevalue(person.fixture)
    probe = PROBES[row.permission]
    want = expected(row, probe, person)
    prepared = probe.prepare(who, stock)
    before = written()

    got = outcome(probe, who, stock, prepared)

    assert got == want
    if want == SAVED:
        assert written() != before, "allowed, yet nothing was written"
    else:
        assert written() == before


# Every other way into a row's action, so no service can skip the check.
# Only the refused cells are tried: an allowed Close would need a batch at 0.
OTHER_WAYS_IN: dict[str, tuple[Permission, Probe]] = {
    "split": (
        Permission.SPLIT_CLOSE_LOSS,
        Probe(lambda who, s, _: split(uuid.uuid4(), who, s.batch, 1, note="sold")),
    ),
    "close": (
        Permission.SPLIT_CLOSE_LOSS,
        Probe(lambda who, s, _: close(uuid.uuid4(), who, s.batch)),
    ),
    "quarantine": (
        Permission.SPLIT_CLOSE_LOSS,
        Probe(lambda who, s, _: log(who, s.batch, "quarantine", qty_out=1)),
    ),
    "void others": (
        Permission.VOID_OR_CORRECT,
        Probe(lambda who, s, _: void(who, s.others_entry, "void_wrong_batch")),
        # A Tech meets the Void tree here, not the row (its own tests).
    ),
    "deactivate": (
        Permission.MANAGE_USERS,
        Probe(lambda who, s, _: deactivate(who, other_tech(), LEFT_THE_COMPANY)),
    ),
    "reactivate": (
        Permission.MANAGE_USERS,
        Probe(lambda who, s, _: reactivate(who, other_tech())),
    ),
    "give_new_password": (
        Permission.MANAGE_USERS,
        Probe(lambda who, s, _: give_new_password(who, other_tech())),
    ),
    "lift_lock": (
        Permission.MANAGE_USERS,
        Probe(lambda who, s, _: lift_lock(who, other_tech())),
    ),
    "set_role": (
        Permission.MANAGE_USERS,
        Probe(lambda who, s, _: set_role(who, other_tech(), Role.SUPERVISOR)),
    ),
    "add_item": (
        Permission.EDIT_REFERENCE_LISTS,
        Probe(lambda who, s, _: add_item(who, ListName.GENERA, "XYZ", "Xyzia")),
    ),
    "switch_off": (
        Permission.EDIT_REFERENCE_LISTS,
        Probe(
            lambda who, s, _: switch_off(
                who, ListName.MEDIA_CODES, "M004", Reason(NO_LONGER_USED)
            )
        ),
    ),
    "switch_on": (
        Permission.EDIT_REFERENCE_LISTS,
        Probe(lambda who, s, _: switch_on(who, ListName.MEDIA_CODES, "M004")),
    ),
}


def other_tech() -> User:
    return User.objects.get(username=OTHER_TECH)


def refused_cells() -> list[tuple[str, Person]]:
    cells = []
    for way, (permission, _) in OTHER_WAYS_IN.items():
        for person in PEOPLE:
            refused_role = person.role not in ROWS[permission].allowed
            if way == "void others" and person.role == Role.TECH:
                continue
            if refused_role or not person.is_active:
                cells.append((way, person))
    return cells


@pytest.mark.parametrize(
    ("way", "person"),
    refused_cells(),
    ids=[f"{way}-{person.fixture}" for way, person in refused_cells()],
)
def test_every_way_into_a_row_is_refused_the_same(
    way: str, person: Person, stock: Stock, request: pytest.FixtureRequest
) -> None:
    who: User = request.getfixturevalue(person.fixture)
    permission, probe = OTHER_WAYS_IN[way]
    before = written()

    got = outcome(probe, who, stock, 0)

    assert got == expected(ROWS[permission], probe, person)
    assert written() == before


@pytest.mark.parametrize(
    "person",
    [person for person in PEOPLE if person.role != Role.ADMIN],
    ids=lambda person: person.fixture,
)
def test_a_refusal_by_role_is_a_403_never_a_refusal_shown_on_the_page(
    person: Person, stock: Stock, request: pytest.FixtureRequest
) -> None:
    """NotAllowed is a PermissionDenied and never a Refused (design §4.1), so
    a view's `except Refused` can't turn it into a message."""
    who: User = request.getfixturevalue(person.fixture)

    with pytest.raises(NotAllowed) as caught:
        reclassify_genus(who, stock.plant, "ANT")

    assert not isinstance(caught.value, Refused)
