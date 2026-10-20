"""Helpers for the U0.2b service tests (U0.2 design §2.5, §3).

Staff with roles, Bangkok dates counted back from today, and stock built
through the event services, so every test starts from numbers the services
worked out themselves.

Dates are real: the `recorded_at` trigger always stamps the database's
`now()`, and backdated entries must stay inside the 7-day window, so the
tests pick dates a few Bangkok days before today.

Loaded for every test through `pytest_plugins` in the root conftest.py.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth.models import Group, User
from django.utils import timezone

from cucumber.accounts.permissions import NotAllowed
from cucumber.batches.models import Batch
from cucumber.core.refusals import Refused
from cucumber.core.tests.rows import run, staff_email
from cucumber.events.services import NewBatch, NewEvent, Saved, save_operation

BANGKOK = ZoneInfo("Asia/Bangkok")


# --------------------------------------------------------------------- staff


def make_staff(name: str, role: str | None, password: str | None = None) -> User:
    """A user in the role's group (design §2.7), or with no role (`None`).

    The user name is an email, as U0.5's `auth_user` rule requires; `name` is
    the person's name. Without a password the account can't log in.

    The role is a plain INSERT, never `groups.add()`: on PostgreSQL that is
    `ON CONFLICT DO NOTHING`, which would hide a second role (U0.6 §6.2).
    """
    email = staff_email(name)
    staff = User.objects.create_user(
        username=email, email=email, password=password, first_name=name
    )
    if role is not None:
        group, _ = Group.objects.get_or_create(name=role)
        User.groups.through.objects.create(user=staff, group=group)
    return staff


@pytest.fixture
def admin() -> User:
    return make_staff("admin", "admin")


@pytest.fixture
def supervisor() -> User:
    return make_staff("supervisor_1", "supervisor")


@pytest.fixture
def other_supervisor() -> User:
    return make_staff("supervisor_2", "supervisor")


@pytest.fixture
def tech() -> User:
    return make_staff("tech_1", "tech")


@pytest.fixture
def other_tech() -> User:
    return make_staff("tech_2", "tech")


@pytest.fixture
def read_only() -> User:
    return make_staff("viewer_1", "read_only")


@pytest.fixture
def no_role() -> User:
    """An account the Admin hasn't given a role yet."""
    return make_staff("new_1", None)


@pytest.fixture
def deactivated_tech() -> User:
    """A Tech whose account was switched off; it keeps its role (U0.6 Q3)."""
    staff = make_staff("tech_off", "tech")
    User.objects.filter(pk=staff.pk).update(is_active=False)
    return staff


# --------------------------------------------------------------------- dates


def days_ago(days: int, hour: int) -> datetime:
    """`hour`:00 in Bangkok, `days` calendar days before today in Bangkok.

    Plain date arithmetic, not the code under test. At least one day back,
    so the time is never in the future.
    """
    assert days >= 1, "pick a past day; use the default (now) for today"
    today = timezone.now().astimezone(BANGKOK).date()
    return datetime.combine(today - timedelta(days=days), time(hour), tzinfo=BANGKOK)


# --------------------------------------------------------------------- stock


def save(by: User, *entries: NewEvent) -> Saved:
    """Save `entries` as one operation with a fresh `operation_id`."""
    return save_operation(uuid.uuid4(), by, entries)


def intake_into_new_batch(
    by: User,
    plant_id: int,
    qty: int,
    *,
    location: str = "nursery",
    stage: str | None = None,
    occurred_at: datetime | None = None,
) -> int:
    """A new batch from an intake of `qty`; returns the batch's id."""
    new_batch = NewBatch(plant_id=plant_id, origin="intake", location_code=location)
    media = "M001" if location == "lab" else None
    entry = NewEvent(
        "intake",
        new_batch=new_batch,
        qty_in=qty,
        stage_to=stage,
        media_code=media,
        occurred_at=occurred_at,
    )
    return save(by, entry).batch_ids[0]


def new_lab_batch(by: User, plant_id: int, qty: int, stage: str = "P2") -> int:
    return intake_into_new_batch(by, plant_id, qty, location="lab", stage=stage)


def log(by: User, batch_id: int, action: str, **values: Any) -> int:
    """One event on an existing batch, in its own operation; returns its id."""
    return save(by, NewEvent(action, batch_id=batch_id, **values)).event_ids[0]


def subculture_entries(
    parent_id: int, plant_id: int, staff_id: int | None = None, children: int = 3
) -> list[NewEvent]:
    """A Subculture using 3 jars of a Lab batch, making child batches of 4 each.

    The units used and the units made differ by design (design §3.1). Each
    child entry makes its own batch, even though the entries are equal.
    """
    used = NewEvent(
        "subculture",
        batch_id=parent_id,
        qty_out=3,
        media_code="M001",
        staff_id=staff_id,
    )
    child = NewBatch(
        plant_id=plant_id,
        origin="subculture",
        location_code="lab",
        parent_batch_id=parent_id,
    )
    made = NewEvent(
        "intake",
        new_batch=child,
        qty_in=4,
        stage_to="P2",
        media_code="M001",
        staff_id=staff_id,
    )
    return [used, *[made] * children]


def batch_of(batch_id: int) -> Batch:
    return Batch.objects.get(pk=batch_id)


def live_count(batch_id: int) -> int:
    return batch_of(batch_id).live_count


# --------------------------------------------------------- committing tests


def restore_reference_rows() -> None:
    """Seed rows the committing tests use, if missing.

    Tests marked `django_db(transaction=True)` commit, and pytest-django
    empties the whole database after each, seed rows included.
    """
    run("""
        INSERT INTO genera (code, name, active) VALUES ('PHL', 'Philodendron', true)
            ON CONFLICT DO NOTHING;
        INSERT INTO locations (code, label, active)
            VALUES ('lab', 'Lab', true), ('nursery', 'Nursery', true)
            ON CONFLICT DO NOTHING;
        INSERT INTO stages (code, label, sort_order, active)
            VALUES ('P2', 'P2', 3, true) ON CONFLICT DO NOTHING;
        INSERT INTO media_codes (code, label, active) VALUES ('M001', 'M001', true)
            ON CONFLICT DO NOTHING;
        INSERT INTO reasons (code, label, applies_to, active)
            VALUES ('void_wrong_batch', 'Wrong batch', 'void', true)
            ON CONFLICT DO NOTHING;
    """)


# ------------------------------------------------------------------ refusals


@contextmanager
def refused(rule: str) -> Iterator[None]:
    """Expect a service to refuse the save inside, naming `rule` (design §7.1)."""
    with pytest.raises(Refused) as caught:
        yield
    assert caught.value.rule == rule, f"expected {rule!r}, refused by {caught.value}"


@contextmanager
def not_allowed(rule: str = "role_not_allowed") -> Iterator[None]:
    """Expect a service to refuse by role or account state (U0.6 design §4.1).

    `NotAllowed` is a 403, not a `Refused`, so `refused()` can't catch it.
    """
    with pytest.raises(NotAllowed) as caught:
        yield
    assert caught.value.rule == rule, f"expected {rule!r}, refused by {caught.value}"
