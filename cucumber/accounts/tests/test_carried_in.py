"""AC16–AC19: four fixes carried in from the U0.5 G4 review (U0.6 design §8)."""

import logging
import re

import pytest
from django.contrib.auth.models import User
from django.test import Client

from cucumber.accounts.permissions import Role
from cucumber.accounts.services import (
    ADDRESS_LIMIT,
    LOCK_AFTER_FAILURES,
    add_account,
    email_key,
    lift_lock,
    login_failed,
)
from cucumber.accounts.tests.helpers import (
    ADDRESS,
    OTHER_ADDRESS,
    PASSWORD,
    add_failures,
    failures,
    failures_from,
    log_in,
    signed_in_as,
)
from cucumber.core.refusals import INTERNAL_MESSAGE, Refused
from cucumber.core.tests.rows import fetch_one, run
from cucumber.core.tests.stock import refused

pytestmark = pytest.mark.django_db

LONGEST_NAME = 150  # auth_user.first_name's size
LONGEST_KEY = 150  # accounts_login_failure.email_key's size


# ------------------------------------------------- AC16 lift a network lock
@pytest.fixture
def lab_locked(gene: User) -> None:
    """Gene's email locked, and the lab's address over its 50-try limit."""
    add_failures("gene@example.com", LOCK_AFTER_FAILURES, ADDRESS)
    add_failures("someone@example.com", ADDRESS_LIMIT, ADDRESS)
    add_failures("pim@example.com", 3, OTHER_ADDRESS)


def test_lifting_the_lock_lifts_a_locked_network_too(
    owner: User, gene: User, lab_locked: None
) -> None:
    lift_lock(owner, gene)

    assert failures("gene@example.com") == 0
    assert failures_from(ADDRESS) == 0
    assert failures_from(OTHER_ADDRESS) == 3  # under its limit: left alone


def test_after_lifting_the_person_can_log_in_from_the_lab(
    owner: User, gene: User, lab_locked: None
) -> None:
    lift_lock(owner, gene)
    client = Client()

    log_in(client, "gene@example.com", PASSWORD, ADDRESS)

    assert signed_in_as(client) == gene.pk


def test_lifting_logs_each_network_it_lifts(
    owner: User, gene: User, lab_locked: None, caplog: pytest.LogCaptureFixture
) -> None:
    """Deleting the rows removes the evidence, so the log keeps it (§8)."""
    caplog.set_level(logging.INFO, logger="cucumber.accounts")

    lift_lock(owner, gene)

    assert f"lock lifted account={gene.pk} by={owner.pk} addresses=1" in (
        caplog.messages
    )
    # The address's own line, with its count (§8); the count depends on
    # whether the email's failures were deleted first, so only its shape.
    assert any(
        ADDRESS in message and re.search(r"\b\d+\b", message.replace(ADDRESS, ""))
        for message in caplog.messages
        if not message.startswith("lock lifted account=")
    )


def test_lifting_with_no_locked_network_lifts_no_address(
    owner: User, gene: User, caplog: pytest.LogCaptureFixture
) -> None:
    add_failures("gene@example.com", LOCK_AFTER_FAILURES, OTHER_ADDRESS)
    caplog.set_level(logging.INFO, logger="cucumber.accounts")

    lift_lock(owner, gene)

    assert failures("gene@example.com") == 0
    assert f"lock lifted account={gene.pk} by={owner.pk} addresses=0" in (
        caplog.messages
    )


# --------------------------------------------------- AC17 names too long
def test_a_name_over_150_characters_is_refused_by_the_service(owner: User) -> None:
    count = User.objects.count()

    with refused("account_name_too_long"):
        add_account(owner, "M" * (LONGEST_NAME + 1), "mali@example.com", Role.TECH)

    assert User.objects.count() == count


def test_a_150_character_name_fits(owner: User) -> None:
    added = add_account(owner, "M" * LONGEST_NAME, "mali@example.com", Role.TECH)

    assert len(User.objects.get(pk=added.account.pk).first_name) == LONGEST_NAME


# ------------------------------------- AC18 a database refusal by its name
def test_only_the_email_rule_says_the_email_is_taken(owner: User) -> None:
    """Another rule the database refuses with is Internal, not "taken"."""
    run(
        "ALTER TABLE auth_user ADD CONSTRAINT test_only_no_refused_name"
        " CHECK (first_name <> 'Refused')"
    )
    count = User.objects.count()

    with pytest.raises(Refused) as caught:
        add_account(owner, "Refused", "mali@example.com", Role.TECH)

    assert caught.value.rule == "test_only_no_refused_name"
    assert caught.value.message == INTERNAL_MESSAGE
    assert User.objects.count() == count


# ------------------------------------------------------- AC19 NFKC emails
@pytest.mark.parametrize(
    ("typed", "key"),
    [
        ("ｊａｄｅ@ｘ.com", "jade@x.com"),  # full-width letters
        (" Jade@Example.COM ", "jade@example.com"),
        ("ｊａｄｅ＠example.com", "jade@example.com"),  # full-width @
        ("ﬁona@example.com", "fiona@example.com"),  # the "fi" ligature
    ],
)
def test_an_email_key_is_normalised_trimmed_and_lowercase(typed: str, key: str) -> None:
    assert email_key(typed) == key


@pytest.mark.parametrize(
    "typed", ["ｊａｄｅ@ｘ.com", "Ⅻ@example.com", " ﬁ@X.com", "ẞtraße@x.com"]
)
def test_making_a_key_twice_changes_nothing(typed: str) -> None:
    assert email_key(email_key(typed)) == email_key(typed)


def test_a_full_width_email_is_stored_and_logs_in_as_plain_letters(
    owner: User,
) -> None:
    added = add_account(owner, "Mali", "ｍａｌｉ@example.com", Role.TECH)
    account = User.objects.get(pk=added.account.pk)
    account.set_password(PASSWORD)
    account.save()
    client = Client()

    log_in(client, "mali@example.com")

    assert account.username == "mali@example.com"
    assert signed_in_as(client) == account.pk


def test_a_failure_key_longer_than_150_after_normalising_is_cut_to_fit() -> None:
    """NFKC can make a key longer: "ﬀ" becomes "ff" (§8)."""
    typed = "ﬀ" * 100 + "@example.com"
    assert len(typed) <= LONGEST_KEY < len(email_key(typed))

    login_failed(typed, ADDRESS)

    stored = fetch_one("SELECT email_key FROM accounts_login_failure")[0]
    assert stored == email_key(typed)[:LONGEST_KEY]
