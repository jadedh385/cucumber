"""Rules for the plants app. Views call these; they never hold rules themselves."""

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Q, QuerySet

from cucumber.accounts.services import ADMIN, has_role
from cucumber.core.refusals import database_refusals, refuse
from cucumber.plants.models import (
    Plant,
    PlantSource,
    PlantStatus,
    PlantStatusChange,
    Sku,
)
from cucumber.references.models import Genus

GENUS_RECLASSIFIED = "genus reclassified"
SKU_DIGITS = 3  # PHL005: the genus code, then 3 digits


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
    if not has_role(admin, ADMIN):
        raise refuse("admin_only")
    with database_refusals(), transaction.atomic():
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


def issue_next_sku(plant_id: int, genus_code: str, assigned_by: User) -> str:
    """Add the genus's next SKU to the register, issued to the plant.

    The next number counts from every SKU ever issued for the genus (Q1).
    The genus row is locked, so two reclassifications into the same genus
    take turns instead of picking the same number. Full sequence rules: U0.8.
    """
    list(Genus.objects.select_for_update(no_key=True).filter(pk=genus_code))
    issued = Sku.objects.filter(genus_id=genus_code).values_list("sku", flat=True)
    highest = max((int(sku[len(genus_code) :]) for sku in issued), default=0)
    sku = f"{genus_code}{highest + 1:0{SKU_DIGITS}d}"
    Sku.objects.create(
        sku=sku, plant_id=plant_id, genus_id=genus_code, assigned_by=assigned_by
    )
    return sku


def find_by_sku(sku: str) -> Plant | None:
    """The plant an SKU was issued to, current or former SKU alike."""
    issued = Sku.objects.select_related("plant").filter(pk=sku).first()
    return issued.plant if issued else None


def former_skus(plant_id: int) -> list[str]:
    """The plant's SKUs other than its current one, oldest first."""
    current = Plant.objects.filter(pk=plant_id).values_list("sku", flat=True).first()
    former = Sku.objects.filter(plant_id=plant_id).exclude(pk=current)
    return list(former.order_by("assigned_at", "sku").values_list("sku", flat=True))
