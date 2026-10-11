"""An entry, once saved, can't be changed or removed: the database refuses."""

import pytest
from django.contrib.auth import get_user_model
from django.db import DatabaseError, connection, transaction

from entries.models import Entry


@pytest.fixture
def entry(db):
    user = get_user_model().objects.create_user("nok", password="pw-for-tests")
    return Entry.objects.create(
        batch_code="BAT-00012",
        action=Entry.Action.SUBCULTURE,
        quantity=30,
        recorded_by=user,
    )


def test_database_refuses_raw_sql_update(entry):
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE entries_entry SET quantity = 99 WHERE id = %s", [entry.id]
            )


def test_database_refuses_raw_sql_delete(entry):
    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM entries_entry WHERE id = %s", [entry.id])


def test_saving_an_existing_entry_through_django_is_refused(entry):
    entry.quantity = 99

    with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
        entry.save()


def test_recorded_at_is_set_by_the_database(entry):
    entry.refresh_from_db()

    assert entry.recorded_at is not None
