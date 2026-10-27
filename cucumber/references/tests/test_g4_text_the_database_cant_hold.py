"""G4 review M1: text the database can't hold is refused by name.

A NUL character (PostgreSQL text holds none) or a lone surrogate (no UTF-8
for it) passed the input checks and came back from the database as a
`DataError` or `UnicodeEncodeError`, outside `database_refusals()`: a page
would show an error, not a message. A label is now refused by its label
rule, and a code by `list_item_unknown`, since no list can hold one.
"""

from collections.abc import Callable

import pytest
from django.contrib.auth.models import User

from cucumber.core.refusals import Refused
from cucumber.references.lists import ListName
from cucumber.references.reading import check_active, item, stage_at_or_after
from cucumber.references.services import add_item, edit_label, switch_off, switch_on
from cucumber.references.tests.support import ARCHIVE_REASON, nothing_written

pytestmark = pytest.mark.django_db

M, C = ListName.MEDIA_CODES, ListName.CONTAINER_TYPES
UNSTORABLE = ["a\x00b", "a\ud800b"]


def rule_of(call: Callable[[], object]) -> str:
    with pytest.raises(Refused) as caught:
        call()
    return caught.value.rule


@pytest.mark.parametrize("text", UNSTORABLE, ids=["nul", "surrogate"])
def test_g4_a_label_the_database_cant_hold_is_refused_by_its_label_rule(
    admin: User, text: str
) -> None:
    with nothing_written(C):
        added = rule_of(lambda: add_item(admin, C, "jiffy_pot", text))
        edited = rule_of(lambda: edit_label(admin, C, "jar", text))

    assert added == edited == "container_types_label_valid"


@pytest.mark.parametrize("text", UNSTORABLE, ids=["nul", "surrogate"])
def test_g4_a_code_the_database_cant_hold_is_not_on_the_list(
    admin: User, text: str
) -> None:
    code = f"M001{text}"
    with nothing_written(M):
        rules = {
            rule_of(lambda: edit_label(admin, M, code, "Half MS")),
            rule_of(lambda: switch_off(admin, M, code, ARCHIVE_REASON)),
            rule_of(lambda: switch_on(admin, M, code)),
        }

    assert rules == {"list_item_unknown"}


@pytest.mark.parametrize("text", UNSTORABLE, ids=["nul", "surrogate"])
def test_g4_the_readers_dont_send_a_code_the_database_cant_hold(text: str) -> None:
    assert rule_of(lambda: check_active(M, "M001", text)) == "list_item_unknown"
    assert item(M, text) is None
    assert rule_of(lambda: stage_at_or_after(text, "P4")) == "list_item_unknown"
    assert rule_of(lambda: stage_at_or_after("P4", text)) == "list_item_unknown"
