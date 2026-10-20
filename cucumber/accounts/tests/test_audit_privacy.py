"""AC8: no audit row holds a password, a hash, a session id or personal data.

Every way an account can change is run once, then every row written is
searched for the people's emails and names, password hashes and the session
keys that existed. Staff are referred to by id only, which is what lets
anonymising (AC12) remove a person without touching the trail.
"""

import json

import pytest
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.test import Client, override_settings

from cucumber.accounts.permissions import Role
from cucumber.accounts.services import (
    add_account,
    deactivate,
    give_new_password,
    lift_lock,
    reactivate,
    set_role,
)
from cucumber.accounts.tests.helpers import (
    NEW_PASSWORD,
    PASSWORD,
    PASSWORD_PAGE,
    add_failures,
    log_in,
)
from cucumber.accounts.tests.test_anonymise import Typed, anonymise_command
from cucumber.accounts.tests.test_audit_writers import UPGRADING_HASHERS
from cucumber.accounts.tests.test_cucumber_admin import Answers, run_command
from cucumber.core.audit import Reason
from cucumber.core.tests.trail import LEFT_COMPANY, audit_mark, audit_rows_since

pytestmark = pytest.mark.django_db

PERSONAL = [
    "jade@example.com", "gene@example.com", "pim@example.com",
    "mali@example.com", "jade", "gene", "pim", "mali", "somchai",
]  # fmt: skip
HASH_MARKS = ["pbkdf2_", "md5$", "argon2", "bcrypt", "sha1$"]


def every_account_change(owner: User, gene: User, pim: User) -> list[str]:
    """Run each change once; returns the session keys seen along the way."""
    log_in(Client(), "gene@example.com", PASSWORD)
    pim_client = Client()
    log_in(pim_client, "pim@example.com", PASSWORD)
    pim_client.post(
        PASSWORD_PAGE,
        {
            "old_password": PASSWORD,
            "new_password1": NEW_PASSWORD,
            "new_password2": NEW_PASSWORD,
        },
    )
    with override_settings(PASSWORD_HASHERS=UPGRADING_HASHERS):
        log_in(Client(), "pim@example.com", NEW_PASSWORD)  # re-hashed at login
    sessions = list(Session.objects.values_list("session_key", flat=True))

    mali = add_account(owner, "Mali Somchai", "mali@example.com", Role.TECH).account
    set_role(owner, mali, Role.SUPERVISOR)
    give_new_password(owner, gene)
    add_failures("pim@example.com", 5)
    lift_lock(owner, pim)
    deactivate(owner, mali, Reason(LEFT_COMPANY, "moved away"))
    reactivate(owner, mali)
    run_command(Answers("jade@example.com"))
    anonymise_command(Typed("mali@example.com"))
    return sessions


def test_no_audit_row_holds_a_secret_or_a_persons_details(
    owner: User, gene: User, pim: User
) -> None:
    mark = audit_mark()

    sessions = every_account_change(owner, gene, pim)

    rows = audit_rows_since(mark)
    assert len(rows) >= 10, "every change should have left a row"
    stored = json.dumps(
        [[row.before, row.after, row.note, row.row_pk] for row in rows]
    ).lower()
    secrets = [*PERSONAL, *HASH_MARKS, *(key.lower() for key in sessions)]
    assert [value for value in secrets if value in stored] == []
