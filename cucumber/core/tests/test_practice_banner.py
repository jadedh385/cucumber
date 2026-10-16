"""AC9: every staging page says "Practice data"; production never does.

The banner is one include, `core/_practice_banner.html`, shown only when the
environment is staging (U0.4a design §4.4). Its style is in cucumber.css.
"""

from pathlib import Path
from typing import Any

import pytest
from django.conf import settings
from django.test import Client, RequestFactory, override_settings
from django.urls import get_resolver

from cucumber.core.context_processors import environment

pytestmark = pytest.mark.django_db

BANNER_TEXT = "PRACTICE DATA"
BANNER_INCLUDE = '{% include "core/_practice_banner.html" %}'
PROCESSOR = "cucumber.core.context_processors.environment"
LOGIN = "/accounts/login/"


def page(path: str) -> str:
    response = Client().get(path)
    return response.content.decode()


def all_templates() -> list[Path]:
    root = Path(settings.BASE_DIR) / "cucumber"
    return sorted(root.glob("*/templates/**/*.html"))


# ------------------------------------------------------- where it is shown
@override_settings(ENVIRONMENT="staging")
def test_staging_pages_show_the_banner_and_say_practice_in_the_title() -> None:
    html = page(LOGIN)

    assert BANNER_TEXT in html
    assert "<title>[Practice]" in html


@pytest.mark.parametrize("name", ["production", "local"])
def test_other_environments_never_show_it(name: str) -> None:
    with override_settings(ENVIRONMENT=name):
        html = page(LOGIN)

    assert BANNER_TEXT not in html
    assert "[Practice]" not in html


@override_settings(ENVIRONMENT="staging")
def test_the_banner_style_comes_from_cucumbers_stylesheet() -> None:
    html = page(LOGIN)

    assert "core/cucumber" in html and ".css" in html


@override_settings(ENVIRONMENT="staging")
def test_a_missing_page_shows_the_banner() -> None:
    response = Client().get("/no-such-page/")

    assert response.status_code == 404
    assert BANNER_TEXT in response.content.decode()


@override_settings(ENVIRONMENT="staging")
def test_the_error_page_shows_the_banner() -> None:
    """Django's own 500 view renders without the request, so it can't."""
    handler = get_resolver().resolve_error_handler(500)

    response = handler(RequestFactory().get("/"))

    assert response.status_code == 500
    assert BANNER_TEXT in response.content.decode()


@override_settings(ENVIRONMENT="production")
def test_the_production_error_page_has_no_banner() -> None:
    handler = get_resolver().resolve_error_handler(500)

    response = handler(RequestFactory().get("/"))

    assert BANNER_TEXT not in response.content.decode()


# ------------------------------------------------------------ how it works
def test_every_page_template_can_see_the_environment() -> None:
    templates: list[dict[str, Any]] = settings.TEMPLATES
    processors = templates[0]["OPTIONS"]["context_processors"]

    assert PROCESSOR in processors


@pytest.mark.parametrize("name", ["local", "staging", "production"])
def test_the_environment_is_given_to_templates(name: str) -> None:
    with override_settings(ENVIRONMENT=name):
        assert environment(RequestFactory().get("/")) == {"environment": name}


def test_plain_404_and_500_pages_exist() -> None:
    templates = Path(settings.BASE_DIR) / "cucumber/core/templates"

    assert (templates / "404.html").is_file()
    assert (templates / "500.html").is_file()


def test_every_full_page_template_includes_the_banner() -> None:
    full_pages = [path for path in all_templates() if "<body" in path.read_text()]
    missing = [
        str(path.relative_to(settings.BASE_DIR))
        for path in full_pages
        if BANNER_INCLUDE not in path.read_text()
    ]

    assert full_pages, "found no page templates: has the folder moved?"
    assert missing == []
