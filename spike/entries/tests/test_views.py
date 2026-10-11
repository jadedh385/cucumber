"""The entry screen works the same way in both UI kits."""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from entries.models import Entry

KITS = ["daisy", "basecoat"]


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user("nok", password="pw-for-tests")


@pytest.fixture
def logged_in(client, user):
    client.force_login(user)
    return client


def valid_form(**overrides):
    data = {
        "batch_code": "BAT-00012",
        "action": Entry.Action.SUBCULTURE,
        "quantity": "30",
        "occurred_on": timezone.localdate().isoformat(),
        "note": "",
    }
    return {**data, **overrides}


@pytest.mark.parametrize("kit", KITS)
def test_page_needs_login(client, db, kit):
    response = client.get(f"/{kit}/")

    assert response.status_code == 302
    assert response.url.startswith(f"/{kit}/login/")


@pytest.mark.parametrize("kit", KITS)
def test_login_page_renders(client, db, kit):
    response = client.get(f"/{kit}/login/")

    assert response.status_code == 200


def test_unknown_kit_is_not_found(logged_in):
    assert logged_in.get("/bootstrap/").status_code == 404


@pytest.mark.parametrize("kit", KITS)
def test_page_shows_the_kit_stylesheet(logged_in, kit):
    response = logged_in.get(f"/{kit}/")

    assert response.status_code == 200
    stylesheet = "daisyui" if kit == "daisy" else "basecoat-css"
    assert stylesheet in response.content.decode()


@pytest.mark.parametrize("kit", KITS)
def test_saving_an_entry_records_who_saved_it(logged_in, user, kit):
    response = logged_in.post(f"/{kit}/entries/", valid_form(), HTTP_HX_REQUEST="true")

    assert response.status_code == 200
    entry = Entry.objects.get()
    assert entry.recorded_by == user
    assert entry.quantity == 30
    assert "BAT-00012" in response.content.decode()


@pytest.mark.parametrize("kit", KITS)
def test_zero_quantity_is_refused_with_a_message(logged_in, kit):
    response = logged_in.post(
        f"/{kit}/entries/", valid_form(quantity="0"), HTTP_HX_REQUEST="true"
    )

    assert response.status_code == 200
    assert Entry.objects.count() == 0
    assert "at least 1" in response.content.decode()


def test_date_more_than_7_days_back_is_refused(logged_in):
    eight_days_ago = timezone.localdate() - datetime.timedelta(days=8)

    response = logged_in.post(
        "/daisy/entries/",
        valid_form(occurred_on=eight_days_ago.isoformat()),
        HTTP_HX_REQUEST="true",
    )

    assert Entry.objects.count() == 0
    assert "7 days" in response.content.decode()


def test_future_date_is_refused(logged_in):
    tomorrow = timezone.localdate() + datetime.timedelta(days=1)

    response = logged_in.post(
        "/daisy/entries/",
        valid_form(occurred_on=tomorrow.isoformat()),
        HTTP_HX_REQUEST="true",
    )

    assert Entry.objects.count() == 0
    assert "future" in response.content.decode()


def test_saving_without_htmx_returns_the_full_page(logged_in):
    response = logged_in.post("/daisy/entries/", valid_form())

    assert response.status_code == 200
    assert "<html" in response.content.decode()
    assert Entry.objects.count() == 1
