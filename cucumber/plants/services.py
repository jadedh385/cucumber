"""Rules for the plants app. Views call these; they never hold rules themselves."""

from django.contrib.auth.models import User
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


def reclassify_genus(admin: User, plant_id: int, genus_code: str) -> Plant:
    """Move a plant to another genus (Admin only; Q1, AC4b, design §2.2).

    A plant with an SKU gets the next SKU for the new genus; its old SKU
    becomes a former SKU, still found by search and never issued again. The
    change is logged in `plant_status_changes` with reason "genus reclassified".
    """
    raise NotImplementedError("U0.2b G3")


def find_by_sku(sku: str) -> Plant | None:
    """The plant an SKU was issued to, current or former SKU alike."""
    raise NotImplementedError("U0.2b G3")


def former_skus(plant_id: int) -> list[str]:
    """The plant's SKUs other than its current one, oldest first."""
    raise NotImplementedError("U0.2b G3")
