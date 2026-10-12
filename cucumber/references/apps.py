from django.apps import AppConfig


class ReferencesConfig(AppConfig):
    """Stages, locations, media codes and other lookup lists (U0.9)."""

    name = "cucumber.references"
    label = "references"
    default_auto_field = "django.db.models.BigAutoField"
