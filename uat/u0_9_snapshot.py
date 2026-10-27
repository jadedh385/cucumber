"""U0.9 G5: what the sandbox data reads as, before and after the deploy.

Piped into `manage.py shell` (`dc run --rm -T migrate python manage.py shell <
uat/u0_9_snapshot.py`). Plain SQL, so it runs on 2026.10.5 and on the branch.
Prints the stage order, the labels, the batches with their projected stage and
count, the events, and the audit row count. Run it twice and compare.
"""

import sys

from django.db import connection

QUERIES = {
    "stages": "SELECT code, label, sort_order, active FROM stages"
    " ORDER BY sort_order NULLS LAST, code",
    "media_codes": "SELECT code, label, active FROM media_codes ORDER BY code",
    "locations": "SELECT code, label, active FROM locations ORDER BY code",
    "genera": "SELECT code, name, active FROM genera ORDER BY code",
    "container_types": "SELECT code, label, active FROM container_types ORDER BY code",
    "batches": "SELECT id, plant_id, location_code, stage_code, live_count, status"
    " FROM batches ORDER BY id",
    "events": "SELECT id, batch_id, action, qty_in, qty_out, counted_qty,"
    " media_code, stage_to FROM events ORDER BY id",
    "audit_log": "SELECT count(*) FROM audit_log",
}


def show(title: str, sql: str) -> None:
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            rows = cursor.fetchall()
    except Exception as failure:  # a table the release does not have yet
        connection.rollback()
        sys.stdout.write(f"## {title}: {type(failure).__name__}: {failure}\n")
        return
    sys.stdout.write(f"## {title} ({len(rows)})\n")
    for row in rows:
        sys.stdout.write("  " + " | ".join(str(value) for value in row) + "\n")


for title, sql in QUERIES.items():
    show(title, sql)
