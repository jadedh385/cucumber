"""AC22-AC25, AC28: the Admin's Staff pages (design §6, §6.2).

The two temporary-password pages answer the POST directly, `no-store`, so
the password never passes through the session or Django's messages.
"""

import logging

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

from cucumber.accounts.tests.helpers import (
    HOME,
    LOGIN,
    PASSWORD,
    STAFF,
    WRONG,
    Response,
    add_failures,
    all_session_data,
    change_due,
    failures,
    log_in,
    redirect_target,
    session_ended,
    signed_in,
    signed_in_as,
    temporary_password_in,
    text,
)
from cucumber.core.tests.stock import make_staff, switch_off
from cucumber.core.tests.trail import LEFT_COMPANY, as_system

pytestmark = pytest.mark.django_db

# U0.7 AC11: the Deactivate button posts a reason from its list.
A_REASON = {"reason_code": LEFT_COMPANY}


def fresh(user: User) -> User:
    return User.objects.get(pk=user.pk)


def assert_never_kept(password: str, response: Response, logs: str) -> None:
    """Shown once in this answer, and nowhere else (§6.2)."""
    assert "no-store" in response["Cache-Control"]
    assert password not in all_session_data()
    assert all(password not in morsel.value for morsel in response.cookies.values())
    assert password not in logs


# ------------------------------------------------------------------- home
def test_the_admin_sees_a_link_to_staff_on_home(owner_client: Client) -> None:
    assert 'href="/staff/"' in text(owner_client.get(HOME))


def test_a_tech_sees_no_link_to_staff(gene_client: Client) -> None:
    assert 'href="/staff/"' not in text(gene_client.get(HOME))


# ------------------------------------------------------------------ list
def test_the_list_shows_every_account_and_its_state(
    owner_client: Client, gene: User, pim: User
) -> None:
    before = text(owner_client.get(STAFF))
    switch_off(pim)
    add_failures("gene@example.com", 5)

    html = text(owner_client.get(STAFF))

    for shown in ["jade", "jade@example.com", "gene@example.com", "pim@example.com"]:
        assert shown in html
    # One more of each than before, whatever the column headings say.
    assert html.count("Deactivated") == before.count("Deactivated") + 1
    assert html.count("Locked") == before.count("Locked") + 1


def test_the_list_takes_as_many_queries_for_ten_accounts_as_for_one(
    owner_client: Client,
) -> None:
    """No look-up per account (G4 L5), even with some wrong tries counted."""
    add_failures("jade@example.com", 2)

    def queries_for_the_list() -> int:
        with CaptureQueriesContext(connection) as queries:
            owner_client.get(STAFF)
        return len(queries.captured_queries)

    for_one = queries_for_the_list()
    for number in range(9):
        add_failures(make_staff(f"staff{number}", "tech").username, 2)

    assert queries_for_the_list() == for_one


def test_an_unknown_account_is_not_found(owner_client: Client) -> None:
    assert owner_client.get(f"{STAFF}99999/").status_code == 404


# ------------------------------------------------------------ detail page
def test_another_accounts_page_has_its_buttons(
    owner_client: Client, gene: User
) -> None:
    html = text(owner_client.get(f"{STAFF}{gene.pk}/"))

    for action in ["deactivate", "new-password", "unlock"]:
        assert f'action="{STAFF}{gene.pk}/{action}/"' in html


def test_a_deactivated_accounts_page_offers_reactivate(
    owner_client: Client, gene: User
) -> None:
    switch_off(gene)

    html = text(owner_client.get(f"{STAFF}{gene.pk}/"))

    assert f'action="{STAFF}{gene.pk}/reactivate/"' in html


def test_your_own_page_has_no_deactivate_or_new_password_button(
    owner_client: Client, owner: User
) -> None:
    html = text(owner_client.get(f"{STAFF}{owner.pk}/"))

    assert f"{STAFF}{owner.pk}/deactivate/" not in html
    assert f"{STAFF}{owner.pk}/new-password/" not in html


# --------------------------------------------------------- AC22 add one
def test_adding_an_account_shows_its_temporary_password_once(
    owner_client: Client, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        response = owner_client.post(
            f"{STAFF}new/",
            {"name": "Mali", "email": " Mali@Example.com ", "role": "tech"},
        )

    assert response.status_code == 200
    password = temporary_password_in(response)
    assert_never_kept(password, response, caplog.text)
    mali = User.objects.get(username="mali@example.com")
    assert change_due(mali)


def test_the_new_person_can_log_in_with_it(owner_client: Client) -> None:
    response = owner_client.post(
        f"{STAFF}new/", {"name": "Mali", "email": "mali@example.com", "role": "tech"}
    )
    client = Client()

    log_in(client, "mali@example.com", temporary_password_in(response))

    assert signed_in_as(client) == User.objects.get(username="mali@example.com").pk


def test_a_taken_email_is_refused_on_the_page(owner_client: Client, gene: User) -> None:
    count = User.objects.count()

    response = owner_client.post(
        f"{STAFF}new/", {"name": "Gene", "email": "GENE@example.com", "role": "tech"}
    )

    assert "Another account already uses this email." in text(response)
    assert User.objects.count() == count


# ---------------------------------------------------- AC23, AC24 on/off
def test_deactivating_ends_the_persons_open_session(
    owner_client: Client, gene: User, gene_client: Client
) -> None:
    response = owner_client.post(f"{STAFF}{gene.pk}/deactivate/", A_REASON)

    assert response.status_code == 302
    assert not fresh(gene).is_active
    assert redirect_target(gene_client.get(HOME))[0] == LOGIN


def test_a_deactivated_person_gets_the_usual_wrong_message(
    owner_client: Client, gene: User
) -> None:
    owner_client.post(f"{STAFF}{gene.pk}/deactivate/", A_REASON)

    response = log_in(Client(), "gene@example.com")

    assert WRONG in text(response)


def test_reactivating_lets_them_back_in(owner_client: Client, gene: User) -> None:
    owner_client.post(f"{STAFF}{gene.pk}/deactivate/", A_REASON)

    owner_client.post(f"{STAFF}{gene.pk}/reactivate/")

    assert fresh(gene).is_active
    assert log_in(Client(), "gene@example.com").status_code == 302


def test_deactivating_yourself_is_refused_on_the_page(
    owner_client: Client, owner: User
) -> None:
    response = owner_client.post(
        f"{STAFF}{owner.pk}/deactivate/", A_REASON, follow=True
    )

    assert "You can't deactivate your own account." in text(response)
    assert fresh(owner).is_active


# --------------------------------------------------- AC25 new password
def test_a_new_password_is_shown_once_and_ends_their_sessions(
    owner_client: Client,
    gene: User,
    gene_client: Client,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG):
        response = owner_client.post(f"{STAFF}{gene.pk}/new-password/")

    assert response.status_code == 200
    password = temporary_password_in(response)
    assert_never_kept(password, response, caplog.text)
    assert fresh(gene).check_password(password)
    assert change_due(gene)
    assert session_ended(gene_client)


def test_giving_yourself_a_new_password_is_refused_on_the_page(
    owner_client: Client, owner: User
) -> None:
    old_hash = fresh(owner).password

    response = owner_client.post(f"{STAFF}{owner.pk}/new-password/", follow=True)

    assert "Change your own password on the Password page." in text(response)
    assert fresh(owner).password == old_hash


def test_the_unlock_button_lifts_the_lock(owner_client: Client, gene: User) -> None:
    add_failures("gene@example.com", 5)

    response = owner_client.post(f"{STAFF}{gene.pk}/unlock/")

    assert response.status_code == 302
    assert failures("gene@example.com") == 0


@pytest.mark.parametrize(
    "action", ["deactivate", "reactivate", "new-password", "unlock"]
)
def test_the_buttons_answer_only_a_form_post(
    owner_client: Client, gene: User, action: str
) -> None:
    before = snapshot(gene)

    response = owner_client.get(f"{STAFF}{gene.pk}/{action}/")

    assert response.status_code == 405
    assert snapshot(gene) == before


@pytest.mark.parametrize("action", ["new/", "{id}/deactivate/", "{id}/new-password/"])
def test_staff_forms_without_a_csrf_token_are_refused(
    owner: User, gene: User, action: str
) -> None:
    client = Client(enforce_csrf_checks=True)
    client.force_login(owner)
    before = snapshot(gene)

    response = send(client, "post", action, gene)

    assert response.status_code == 403
    assert snapshot(gene) == before


# ------------------------------------------- AC28 nobody else, nothing changes
STAFF_REQUESTS = [
    ("get", ""),
    ("get", "new/"),
    ("post", "new/"),
    ("get", "{id}/"),
    ("post", "{id}/deactivate/"),
    ("post", "{id}/reactivate/"),
    ("post", "{id}/new-password/"),
    ("post", "{id}/unlock/"),
]


@pytest.fixture
def target(pim: User) -> User:
    """A deactivated, locked account, so every button has something to change."""
    switch_off(pim)
    add_failures("pim@example.com", 5)
    return fresh(pim)


def snapshot(target: User) -> tuple[object, ...]:
    account = fresh(target)
    return (
        account.is_active,
        account.password,
        change_due(account),
        failures(account.username),
        User.objects.count(),
    )


def send(client: Client, method: str, address: str, target: User) -> Response:
    path = STAFF + address.format(id=target.pk)
    data = {"name": "Mali", "email": "mali@example.com"} if method == "post" else {}
    response: Response = getattr(client, method)(path, data)
    return response


@pytest.mark.parametrize(("method", "address"), STAFF_REQUESTS)
def test_a_tech_is_refused_every_staff_page(
    gene: User, target: User, method: str, address: str
) -> None:
    before = snapshot(target)

    response = send(signed_in(gene), method, address, target)

    assert response.status_code == 403
    assert snapshot(target) == before


@pytest.mark.parametrize(("method", "address"), STAFF_REQUESTS)
def test_someone_signed_out_is_sent_to_login_from_every_staff_page(
    target: User, method: str, address: str
) -> None:
    before = snapshot(target)

    response = send(Client(), method, address, target)

    assert response.status_code == 302
    assert redirect_target(response)[0] == LOGIN
    assert snapshot(target) == before


def test_a_new_account_without_a_role_sees_only_home(owner: User) -> None:
    with as_system():
        mali = User.objects.create_user(
            username="mali@example.com", email="mali@example.com", password=PASSWORD
        )
    client = signed_in(mali)

    assert client.get(HOME).status_code == 200
    assert client.get(STAFF).status_code == 403


# ---------------------------------------------------------- G4 review (M1)
def test_reactivating_does_not_bring_back_old_sessions(
    owner_client: Client, gene: User, gene_client: Client
) -> None:
    """A lost phone stays signed out after the account is switched back on."""
    owner_client.post(f"{STAFF}{gene.pk}/deactivate/", A_REASON)

    owner_client.post(f"{STAFF}{gene.pk}/reactivate/")

    assert session_ended(gene_client)


def test_deactivating_ends_only_that_persons_sessions(
    owner_client: Client, gene: User, gene_client: Client, pim: User
) -> None:
    pim_client = signed_in(pim)

    owner_client.post(f"{STAFF}{gene.pk}/deactivate/", A_REASON)

    assert signed_in_as(owner_client) is not None
    assert not session_ended(owner_client)
    assert not session_ended(pim_client)
