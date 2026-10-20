"""AC11, spec Q3: deactivating an account needs a reason (design §6, §10).

The service checks first, so the Admin gets a message instead of a database
error; the database rule behind it is in core's test_reason_rule.py.
"""

import re

import pytest
from django.contrib.auth.models import User
from django.test import Client

from cucumber.accounts.services import deactivate
from cucumber.accounts.tests.helpers import STAFF, session_ended, text
from cucumber.core.audit import LONGEST_NOTE, Reason
from cucumber.core.tests.stock import refused
from cucumber.core.tests.trail import (
    LEFT_COMPANY,
    NEW_REASONS,
    NO_LONGER_USED,
    PDPA_CODE,
    audit_mark,
    audit_rows_since,
    only_row,
)

pytestmark = pytest.mark.django_db

CHOOSE = "Choose a reason."
WRONG_LIST = "That reason doesn't fit this change. Choose another."
TOO_LONG = "The note can be at most 500 characters."
HINT = "Don't write names or health details here: notes are kept for good."


def is_active(user: User) -> bool:
    return User.objects.get(pk=user.pk).is_active


# ----------------------------------------------------------- the service
def test_no_reason_is_refused_and_nothing_changes(owner: User, gene: User) -> None:
    mark = audit_mark()

    with refused("reason_required"):
        deactivate(owner, gene, None)

    assert is_active(gene)
    assert audit_rows_since(mark) == []


@pytest.mark.parametrize("code", [NO_LONGER_USED, "void_duplicate_entry", "made_up"])
def test_a_reason_from_another_list_is_refused(
    owner: User, gene: User, code: str
) -> None:
    with refused("reason_wrong_list"):
        deactivate(owner, gene, Reason(code))

    assert is_active(gene)


def test_the_pdpa_reason_is_for_anonymising_only(owner: User, gene: User) -> None:
    """It is inactive on the list: no page offers it (design §5.1)."""
    with refused("reason_wrong_list"):
        deactivate(owner, gene, Reason(PDPA_CODE))

    assert is_active(gene)


def test_a_note_over_500_characters_is_refused(owner: User, gene: User) -> None:
    with refused("reason_note_too_long"):
        deactivate(owner, gene, Reason(LEFT_COMPANY, "x" * (LONGEST_NOTE + 1)))

    assert is_active(gene)


def test_with_a_reason_the_account_is_off_and_its_sessions_end(
    owner: User, gene: User, gene_client: Client
) -> None:
    deactivate(owner, gene, Reason(LEFT_COMPANY, "  moved to Chiang Mai  "))

    assert not is_active(gene)
    assert session_ended(gene_client)


def test_the_old_refusals_still_come_first(owner: User) -> None:
    """Your own account is refused whatever the reason (U0.5 AC24)."""
    with refused("account_cannot_deactivate_self"):
        deactivate(owner, owner, Reason(LEFT_COMPANY))


# --------------------------------------------------------------- the page
def page(client: Client, account: User) -> str:
    return text(client.get(f"{STAFF}{account.pk}/"))


def post(client: Client, account: User, **data: str) -> str:
    response = client.post(f"{STAFF}{account.pk}/deactivate/", data, follow=True)
    return text(response)


def test_the_page_offers_the_four_reasons_and_a_note(
    owner_client: Client, gene: User
) -> None:
    html = page(owner_client, gene)

    select = re.search(r'<select name="reason_code".*?</select>', html, re.S)
    assert select is not None, "no reason picker"
    options = re.findall(r'<option value="([^"]*)"[^>]*>([^<]*)</option>', select[0])
    assert options[0] == ("", "Choose a reason")
    assert [label for _, label in options[1:]] == NEW_REASONS["deactivate"]
    assert PDPA_CODE not in select[0]
    assert 'name="note"' in html
    assert HINT in html


def test_posting_without_a_reason_shows_the_message_and_changes_nothing(
    owner_client: Client, gene: User
) -> None:
    html = post(owner_client, gene)

    assert CHOOSE in html
    assert is_active(gene)


def test_posting_with_a_reason_deactivates_and_records_it(
    owner_client: Client, owner: User, gene: User
) -> None:
    mark = audit_mark()

    html = post(owner_client, gene, reason_code=LEFT_COMPANY, note="moved away")

    assert "gene's account is deactivated." in html
    assert not is_active(gene)
    row = only_row(mark, "auth_user")
    assert (row.actor_id, row.reason_code, row.note) == (
        owner.pk,
        LEFT_COMPANY,
        "moved away",
    )


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"reason_code": NO_LONGER_USED}, WRONG_LIST),
        ({"reason_code": LEFT_COMPANY, "note": "x" * (LONGEST_NOTE + 1)}, TOO_LONG),
    ],
    ids=["wrong list", "long note"],
)
def test_the_other_reason_refusals_show_on_the_page(
    owner_client: Client, gene: User, data: dict[str, str], message: str
) -> None:
    html = post(owner_client, gene, **data)

    assert message in html
    assert is_active(gene)
