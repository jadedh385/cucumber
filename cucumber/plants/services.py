"""Rules for the plants app. Views call these; they never hold rules themselves."""

from django.db.models import Q, QuerySet

from cucumber.plants.models import Plant, PlantSource, PlantStatus


def zoho_link_missing() -> QuerySet[Plant]:
    """Purchased plants still missing their vendor or Zoho reference (Q2, AC5).

    The Admin's weekly "Zoho link missing" list: `source = 'purchase'` and no
    vendor or no `zoho_ref`, leaving out voided plants (design §2.2).
    """
    return (
        Plant.objects.filter(source=PlantSource.PURCHASE)
        .filter(Q(vendor__isnull=True) | Q(zoho_ref__isnull=True))
        .exclude(status=PlantStatus.VOIDED)
        .order_by("id")
    )
