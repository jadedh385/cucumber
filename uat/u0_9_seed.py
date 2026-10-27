"""U0.9 G5: sandbox data for staging, made before the deploy.

Piped into `manage.py shell` in the running release's migrate container
(`dc run --rm -T migrate python manage.py shell < uat/u0_9_seed.py`). It uses
only services the running release (2026.10.5) already has: four batches at
stage P1 or P2 in the lab, on media M001 and M004, each with its events, saved
by the U0.8 sandbox Tech on the U0.8 sandbox plants (`uat/u0_8_seed.py`).
"""

import sys
import uuid

from django.contrib.auth.models import User

from cucumber.events.services import NewBatch, NewEvent, save_operation

TECH = "g5-sandbox-tech@example.com"
PLANT_IDS = (1, 2, 3)  # PHL001 to PHL003, made by the U0.8 seed
LOCATION = "lab"

tech = User.objects.get(username=TECH)


def intake(plant_id: int, qty: int, stage: str, media: str) -> NewEvent:
    new = NewBatch(plant_id=plant_id, origin="intake", location_code=LOCATION)
    return NewEvent(
        "intake", new_batch=new, qty_in=qty, stage_to=stage, media_code=media
    )


def run(entries: list[NewEvent]) -> tuple[int, ...]:
    saved = save_operation(uuid.uuid4(), tech, entries)
    sys.stdout.write(f"batches {saved.batch_ids} events {saved.event_ids}\n")
    return saved.batch_ids


a = run([intake(PLANT_IDS[0], 12, "P1", "M001")])[0]
run([NewEvent("count", batch_id=a, counted_qty=12)])

b = run([intake(PLANT_IDS[1], 10, "P1", "M004")])[0]
run([NewEvent("subculture", batch_id=b, qty_out=2, media_code="M004")])

run([intake(PLANT_IDS[2], 8, "P2", "M004")])

d = run([intake(PLANT_IDS[0], 6, "P1", "M001")])[0]
run([NewEvent("stage_change", batch_id=d, stage_to="P2")])
