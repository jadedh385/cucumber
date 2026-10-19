"""AC25-AC27: choosing your own password, forced or not (design §5, §7.4).

Django's PasswordChangeForm fields: old_password, new_password1, new_password2.
"""

import pytest
from django.contrib.auth.models import User
from django.test import Client

from cucumber.accounts.tests.helpers import (
    HOME,
    LOGOUT,
    NEW_PASSWORD,
    PASSWORD,
    PASSWORD_PAGE,
    STAFF,
    Response,
    change_due,
    htmx_headers,
    log_in,
    mark_change_due,
    redirect_target,
    session_ended,
    signed_in,
    signed_in_as,
    text,
)

pytestmark = pytest.mark.django_db


def change(client: Client, old: str, new: str) -> Response:
    response: Response = client.post(
        PASSWORD_PAGE, {"old_password": old, "new_password1": new, "new_password2": new}
    )
    return response


@pytest.fixture
def due_client(gene: User) -> Client:
    """Gene, signed in with a temporary password still to change."""
    mark_change_due(gene)
    return signed_in(gene)


# ------------------------------------------------------ AC25 forced change
@pytest.mark.parametrize("address", [HOME, STAFF, "/staff/1/"])
def test_every_page_sends_you_to_choose_a_password_first(
    due_client: Client, address: str
) -> None:
    response = due_client.get(address)

    assert response.status_code == 302
    assert redirect_target(response)[0] == PASSWORD_PAGE


def test_the_password_page_itself_opens(due_client: Client) -> None:
    response = due_client.get(PASSWORD_PAGE)

    assert response.status_code == 200
    assert "Choose your own password" in text(response)


def test_you_can_still_log_out(due_client: Client) -> None:
    due_client.post(LOGOUT)

    assert signed_in_as(due_client) is None


def test_htmx_while_a_change_is_due_gets_401_and_hx_redirect(
    due_client: Client,
) -> None:
    response = due_client.post("/staff/new/", headers=htmx_headers())

    assert response.status_code == 401
    assert redirect_target(response) == (PASSWORD_PAGE, {"next": ["/staff/"]})


def test_the_check_reads_the_table_on_every_page(
    gene_client: Client, gene: User
) -> None:
    """A row added after login (U0.6, a command, a hand fix) counts at once."""
    assert gene_client.get(HOME).status_code == 200

    mark_change_due(gene)

    assert redirect_target(gene_client.get(HOME))[0] == PASSWORD_PAGE


def test_choosing_a_password_clears_the_change(due_client: Client, gene: User) -> None:
    response = change(due_client, PASSWORD, NEW_PASSWORD)

    assert response.status_code == 302
    assert not change_due(gene)
    assert due_client.get(HOME).status_code == 200


def test_the_temporary_password_cant_be_chosen_again(
    due_client: Client, gene: User
) -> None:
    """Or the Admin would still know it (§7.4)."""
    response = change(due_client, PASSWORD, PASSWORD)

    assert "Choose a password different from the one you were given." in text(response)
    assert change_due(gene)


# ------------------------------------------------------- AC26 own change
def test_changing_your_password_keeps_this_session_and_ends_the_others(
    gene: User,
) -> None:
    this_phone = signed_in(gene)
    other_phone = signed_in(gene)

    change(this_phone, PASSWORD, NEW_PASSWORD)

    assert signed_in_as(this_phone) == gene.pk
    assert this_phone.get(HOME).status_code == 200
    assert session_ended(other_phone)
    assert log_in(Client(), "gene@example.com", NEW_PASSWORD).status_code == 302


def test_the_current_password_must_be_right(gene_client: Client, gene: User) -> None:
    change(gene_client, "not-the-password", NEW_PASSWORD)

    assert User.objects.get(pk=gene.pk).check_password(PASSWORD)


def test_a_password_change_without_a_csrf_token_is_refused(gene: User) -> None:
    client = Client(enforce_csrf_checks=True)
    client.force_login(gene)

    response = client.post(
        PASSWORD_PAGE,
        {
            "old_password": PASSWORD,
            "new_password1": NEW_PASSWORD,
            "new_password2": NEW_PASSWORD,
        },
    )

    assert response.status_code == 403
    assert User.objects.get(pk=gene.pk).check_password(PASSWORD)


# ------------------------------------------------------- AC27 four rules
@pytest.mark.parametrize(
    ("weak", "message"),
    [
        ("short1", "This password is too short."),
        ("password123", "This password is too common."),
        ("4815162342", "This password is entirely numeric."),
        ("gene@example.com", "The password is too similar to the"),
    ],
)
def test_weak_new_passwords_are_refused(
    gene_client: Client, gene: User, weak: str, message: str
) -> None:
    response = change(gene_client, PASSWORD, weak)

    assert response.status_code == 200
    assert message in text(response)
    assert User.objects.get(pk=gene.pk).check_password(PASSWORD)
