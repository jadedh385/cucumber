from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Shared helpers, the health page and base templates."""

    name = "cucumber.core"
    label = "core"
    default_auto_field = "django.db.models.BigAutoField"
