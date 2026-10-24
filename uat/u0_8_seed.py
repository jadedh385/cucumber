"""U0.8 G5: sandbox data for staging, made before the deploy.

Piped into `manage.py shell` in the running release's migrate container
(`dc run --rm -T migrate python manage.py shell < uat/u0_8_seed.py`). It uses
only the release's own services, so it runs on 2026.10.4 and leaves the id
generators part-way along. Three plants with SKUs, three batches, a few events.
"""

import sys
import uuid

from django.contrib.auth.models import User
from django.db import connection

from cucumber.accounts.permissions import Role
from cucumber.accounts.services import replace_role
from cucumber.core.audit import SYSTEM, audited
from cucumber.events.services import NewBatch, NewEvent, save_operation

VIA = "g5-seed"
EMAIL = "g5-sandbox-tech@example.com"
PLANTS = (
    ("Pink Princess", "PHL001"),
    ("Pink Princess B", "PHL002"),
    ("Pink Princess C", "PHL003"),
)


def make_plant(name: str, sku: str, tech_id: int) -> int:
    """A Collection plant given as a gift, and its SKU (plain SQL, as the owner)."""
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO plants (genus_code, full_name, status, source, notes,"
            " created_at, created_by)"
            " VALUES ('PHL', %s, 'collection', 'gift', '', now(), %s) RETURNING id",
            [name, tech_id],
        )
        row = cursor.fetchone()
        if row is None:
            raise SystemExit(f"no id back for the plant {name!r}")
        plant_id = int(row[0])
        cursor.execute(
            "INSERT INTO skus (sku, plant_id, genus_code, assigned_at, assigned_by)"
            " VALUES (%s, %s, 'PHL', now(), %s)",
            [sku, plant_id, tech_id],
        )
        cursor.execute("UPDATE plants SET sku = %s WHERE id = %s", [sku, plant_id])
    return plant_id


with audited(SYSTEM, via=VIA):
    tech, _ = User.objects.get_or_create(username=EMAIL, defaults={"email": EMAIL})
    replace_role(tech, Role("tech"))
    plant_ids = [make_plant(name, sku, tech.pk) for name, sku in PLANTS]

for plant_id in plant_ids:
    new = NewBatch(plant_id=plant_id, origin="intake", location_code="lab")
    intake = NewEvent(
        "intake", new_batch=new, qty_in=12, stage_to="P0", media_code="M001"
    )
    saved = save_operation(uuid.uuid4(), tech, [intake])
    batch_id = saved.batch_ids[0]
    stage = NewEvent("stage_change", batch_id=batch_id, stage_to="P1")
    save_operation(uuid.uuid4(), tech, [stage])
    sys.stdout.write(f"plant {plant_id} batch {batch_id} events {saved.event_ids}\n")
