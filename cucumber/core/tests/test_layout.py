"""AC11: one app per feature under cucumber/, each with its own tests."""

from pathlib import Path

from django.conf import settings

FEATURE_APPS = {"accounts", "batches", "core", "events", "plants", "references"}
PROJECT_DIR = Path(settings.BASE_DIR) / "cucumber"


def app_folders() -> list[Path]:
    """Every folder under cucumber/ that is a Django app (has an apps.py)."""
    return sorted(path.parent for path in PROJECT_DIR.glob("*/apps.py"))


def test_every_feature_has_an_app() -> None:
    found = {folder.name for folder in app_folders()}
    assert sorted(FEATURE_APPS - found) == []


def test_every_feature_app_is_installed() -> None:
    expected = {f"cucumber.{name}" for name in FEATURE_APPS}
    assert sorted(expected - set(settings.INSTALLED_APPS)) == []


def test_every_app_has_a_tests_folder() -> None:
    missing = [
        folder.name
        for folder in app_folders()
        if not (folder / "tests" / "__init__.py").is_file()
    ]
    assert missing == []


def test_every_app_has_a_services_module_for_its_rules() -> None:
    missing = [
        folder.name
        for folder in app_folders()
        if not (folder / "services.py").is_file()
    ]
    assert missing == []
