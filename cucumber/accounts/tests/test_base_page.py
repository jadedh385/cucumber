"""AC6, AC21: the base page every signed-in screen uses, and text marked for Thai.

The "Practice data" banner on every full page is already checked for every
template by core's test_practice_banner.py.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client, override_settings

from cucumber.accounts.tests.helpers import (
    HOME,
    PASSWORD,
    PASSWORD_PAGE,
    STAFF,
    Response,
    shows_signed_in,
    signed_in,
    text,
)
from cucumber.core.tests.trail import as_system

TEMPLATES = Path(settings.BASE_DIR) / "cucumber/accounts/templates"
DESIGNED_TEMPLATES = [
    "base.html",
    "accounts/home.html",
    "accounts/password.html",
    "registration/login.html",
]
# Parts of a template that are not text a person reads, or are already
# marked for translation. Removed before looking for left-over words.
NOT_TEXT = [
    r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}",
    r"{#.*?#}",
    r"<style\b.*?</style>",
    r"<script\b.*?</script>",
    r"{%\s*blocktranslate\b.*?{%\s*endblocktranslate\s*%}",
    r"{%.*?%}",
    r"{{.*?}}",
    r"<[^>]*>",
    r"&\w+;",
]
# The app's name stays the same in Thai.
NAMES = {"Cucumber"}
READABLE_ATTRIBUTES = re.compile(
    r'\b(?:placeholder|aria-label|title|alt)="([^"]*[A-Za-z][^"]*)"'
)


def template_files() -> list[Path]:
    return sorted(TEMPLATES.glob("**/*.html"))


def words_not_marked(source: str) -> list[str]:
    readable = [
        value
        for value in READABLE_ATTRIBUTES.findall(source)
        if "{%" not in value and "{{" not in value
    ]
    for pattern in NOT_TEXT:
        source = re.sub(pattern, " ", source, flags=re.DOTALL)
    words = re.findall(r"[A-Za-z][A-Za-z'’]*", source)
    return readable + [word for word in words if word not in NAMES]


# ------------------------------------------------------------ templates
@pytest.mark.parametrize("name", DESIGNED_TEMPLATES)
def test_the_designed_templates_exist(name: str) -> None:
    assert (TEMPLATES / name).is_file()


def test_the_staff_pages_have_their_templates() -> None:
    """List, add and detail at least (design §1)."""
    assert len(list((TEMPLATES / "accounts").glob("staff_*.html"))) >= 3


def test_every_word_on_the_account_pages_is_marked_for_translation() -> None:
    """D-16: Thai to follow, so all text goes through gettext (AC6)."""
    unmarked = {
        str(path.relative_to(TEMPLATES)): words
        for path in template_files()
        if (words := words_not_marked(path.read_text()))
    }

    assert template_files(), "no account templates found"
    assert unmarked == {}


def test_the_translation_check_finds_plain_text() -> None:
    """Proves the check above would catch an unmarked word."""
    assert words_not_marked("<p>Log in</p>") == ["Log", "in"]
    assert words_not_marked('<input placeholder="Email">') == ["Email"]
    assert words_not_marked("<p>{% translate 'Log in' %}</p>") == []
    assert (
        words_not_marked("{% blocktranslate %}Hi {{ n }}{% endblocktranslate %}") == []
    )


# ----------------------------------------------------------- AC21 base
SIGNED_IN_PAGES = [HOME, PASSWORD_PAGE, STAFF, f"{STAFF}new/"]


def logout_form(response: Response) -> str:
    found = re.search(r'<form\b[^>]*action="/accounts/logout/"[^>]*>', text(response))
    assert found, "no logout form"
    return found.group(0)


@pytest.mark.django_db
@pytest.mark.parametrize("address", SIGNED_IN_PAGES)
def test_signed_in_pages_use_the_base_page(owner_client: Client, address: str) -> None:
    response = owner_client.get(address)

    assert response.status_code == 200
    assert "base.html" in [template.name for template in response.templates]
    assert "Cucumber" in text(response)
    assert shows_signed_in(text(response), "jade")
    assert 'method="post"' in logout_form(response).lower()


@pytest.mark.django_db
def test_the_logout_button_carries_a_csrf_token(owner_client: Client) -> None:
    response = owner_client.get(HOME)
    html = text(response)
    start = html.index(logout_form(response))
    form = html[start : html.index("</form>", start)]

    assert 'name="csrfmiddlewaretoken"' in form


@pytest.mark.django_db
def test_an_account_without_a_name_is_shown_by_its_email(db: None) -> None:
    with as_system():
        nameless = User.objects.create_user(
            username="nn@example.com", email="nn@example.com", password=PASSWORD
        )

    html = text(signed_in(nameless).get(HOME))

    assert shows_signed_in(html, "nn@example.com")


@pytest.mark.django_db
@override_settings(ENVIRONMENT="staging")
def test_the_home_page_shows_the_practice_banner_on_staging(
    gene_client: Client,
) -> None:
    assert "PRACTICE DATA" in text(gene_client.get(HOME))
