from django.apps import AppConfig


class EventsConfig(AppConfig):
    """Everything that happens to plants and batches; never edited or deleted (U0.2)."""

    name = "cucumber.events"
    label = "events"
    default_auto_field = "django.db.models.BigAutoField"
