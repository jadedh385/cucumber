from django.apps import AppConfig
from django.contrib.auth.signals import user_logged_in, user_logged_out


class AccountsConfig(AppConfig):
    """Staff accounts and logging in (U0.5)."""

    name = "cucumber.accounts"
    label = "accounts"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        from cucumber.accounts.signals import note_logout, stamp_login

        user_logged_in.connect(stamp_login, dispatch_uid="accounts_stamp_login")
        user_logged_out.connect(note_logout, dispatch_uid="accounts_note_logout")
