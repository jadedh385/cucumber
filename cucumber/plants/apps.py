from django.apps import AppConfig


class PlantsConfig(AppConfig):
    """Plants and their SKUs (U0.2a)."""

    name = "cucumber.plants"
    label = "plants"
    default_auto_field = "django.db.models.BigAutoField"
