"""Rules for the plants app. Views call these; they never hold rules themselves."""

from django.contrib.auth.models import User
from django.db.models import Q, QuerySet

from cucumber.accounts.permissions import Permission, require
from cucumber.core.audit import audited
from cucumber.core.refusals import database_refusals, refuse
from cucumber.ids.issuing import issue_next_sku
from cucumber.plants.models import (
    Plant,
    PlantSource,
    PlantStatus,
    PlantStatusChange,
    Sku,
)
from cucumber.references.lists import ListName
from cucumber.references.reading import check_active

GENUS_RECLASSIFIED = "genus reclassified"


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
    with database_refusals(), audited(admin):
        require(admin, Permission.RECLASSIFY_GENUS)
        check_active(ListName.GENERA, genus_code)  # the genus is picked (U0.9 AC13)
        plant = Plant.objects.select_for_update(no_key=True).filter(pk=plant_id).first()
        if plant is None:
            raise refuse("plant_not_found")
        if plant.genus_id == genus_code:
            raise refuse("plant_same_genus")
        new_sku = None
        if plant.sku_id is not None:
            # The (sku, id) link is checked at once: issue the SKU first (§3.4).
            new_sku = issue_next_sku(plant_id, genus_code, admin)
        # Genus and SKU change in one update, as the static-SKU trigger needs.
        changes = {"genus_id": genus_code, "sku_id": new_sku or plant.sku_id}
        Plant.objects.filter(pk=plant_id).update(**changes)
        PlantStatusChange.objects.create(
            plant_id=plant_id,
            from_status=plant.status,
            to_status=plant.status,
            sku_assigned=new_sku,
            changed_by=admin,
            reason=GENUS_RECLASSIFIED,
        )
    return Plant.objects.get(pk=plant_id)


def former_skus(plant_id: int) -> list[str]:
    """The plant's SKUs other than its current one, oldest first."""
    current = Plant.objects.filter(pk=plant_id).values_list("sku", flat=True).first()
    former = Sku.objects.filter(plant_id=plant_id).exclude(pk=current)
    return list(former.order_by("assigned_at", "sku").values_list("sku", flat=True))
