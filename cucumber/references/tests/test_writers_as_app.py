"""The writers work with only the app user's rights (design §2.3, §3.3).

The other writer tests run as the tables' owner, whom `cucumber_owner_only`
lets through, so `stages_order_fixed` and `locations_fixed` never fire there.
Here Django's own connection is `cucumber_app` (`as_app_user`, root
conftest.py): a writer that saves a whole row, or a missing UPDATE grant on
`container_types`, would fail here as it would on the servers.
"""

import pytest
from django.contrib.auth.models import Group, User

from cucumber.accounts.permissions import Role
from cucumber.accounts.tests.helpers import PASSWORD
from cucumber.core.audit import Reason
from cucumber.core.tests.rows import run
from cucumber.core.tests.stock import make_staff, restore_reference_rows
from cucumber.core.tests.trail import NO_LONGER_USED, as_system
from cucumber.references.lists import ListName
from cucumber.references.reading import Item, item
from cucumber.references.services import add_item, edit_label, switch_off, switch_on

pytestmark = pytest.mark.django_db(transaction=True)

ARCHIVE = Reason(NO_LONGER_USED)


@pytest.fixture
def owner_admin() -> User:
    """The Admin and the rows the writers change, made as the owner first.

    The flush before this test emptied the lists, groups and reasons.
    """
    for role in Role:
        Group.objects.get_or_create(name=role)
    restore_reference_rows()
    with as_system():
        run(
            "INSERT INTO reasons (code, label, applies_to, active)"
            " VALUES (%s, 'No longer used', 'archive', true) ON CONFLICT DO NOTHING",
            [NO_LONGER_USED],
        )
    return make_staff("jade", "admin", PASSWORD)


def test_every_writer_works_as_the_app_user(
    owner_admin: User, as_app_user: None
) -> None:
    edit_label(owner_admin, ListName.STAGES, "P2", "Growth")
    edit_label(owner_admin, ListName.LOCATIONS, "lab", "The Lab")
    add_item(owner_admin, ListName.CONTAINER_TYPES, "jiffy_pot", "Jiffy pot")
    edit_label(owner_admin, ListName.CONTAINER_TYPES, "jiffy_pot", "Jiffy pot 6 cm")
    for name, code in [(ListName.MEDIA_CODES, "M001"), (ListName.STAGES, "P2")]:
        switch_off(owner_admin, name, code, ARCHIVE)
        switch_on(owner_admin, name, code)
    switch_off(owner_admin, ListName.CONTAINER_TYPES, "jiffy_pot", ARCHIVE)

    assert item(ListName.STAGES, "P2") == Item("P2", "Growth", True, 3)
    assert item(ListName.LOCATIONS, "lab") == Item("lab", "The Lab", True)
    assert item(ListName.MEDIA_CODES, "M001") == Item("M001", "M001", True)
    assert item(ListName.CONTAINER_TYPES, "jiffy_pot") == Item(
        "jiffy_pot", "Jiffy pot 6 cm", False
    )
