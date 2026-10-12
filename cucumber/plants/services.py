"""Rules for the plants app. Views call these; they never hold rules themselves."""

from django.db.models import Model, QuerySet


def zoho_link_missing() -> QuerySet[Model]:
    """Purchased plants still missing their vendor or Zoho reference (Q2, AC5).

    The Admin's weekly "Zoho link missing" list: `source = 'purchase'` and no
    vendor or no `zoho_ref`, leaving out voided plants (design §2.2).
    """
    raise NotImplementedError("U0.2a G3")
