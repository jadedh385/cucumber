from django.apps import AppConfig


class BatchesConfig(AppConfig):
    """Batches of plants (U0.2a)."""

    name = "cucumber.batches"
    label = "batches"
    default_auto_field = "django.db.models.BigAutoField"
