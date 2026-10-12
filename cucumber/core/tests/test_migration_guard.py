"""G4 (H1): undoing the schema migrations is refused while there is data.

Reversing U0.2a's migrations drops the tables, and triggers don't fire on a
drop, so history would be lost. The last migration refuses to be undone
while any history or plant data exists (design §6).
"""

import importlib

import pytest
from django.apps import apps

from cucumber.core.tests.rows import make_plant

guard = importlib.import_module(
    "cucumber.core.migrations.0004_refuse_reverse_with_data"
)

pytestmark = pytest.mark.django_db


def test_undo_is_allowed_on_an_empty_database() -> None:
    guard.refuse_if_data(apps, None)


def test_undo_is_refused_once_a_plant_exists(user: int) -> None:
    make_plant(user)
    with pytest.raises(RuntimeError, match="plants"):
        guard.refuse_if_data(apps, None)
