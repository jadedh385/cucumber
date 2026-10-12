"""Event rules Django can't declare (design §2.4, §2.5, §4).

- `recorded_at` is always the real save time, whatever the app sends (M1, N6).
- A Void or Correction stays on the batch of the event it fixes.
- Events, operations and reviews are insert-only (rule 8, Q3).
"""

from django.db import migrations

from cucumber.core import db_rules

RECORDED_AT_NOW = """
CREATE FUNCTION events_recorded_at_now() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  NEW.recorded_at := now();
  RETURN NEW;
END $$;

CREATE TRIGGER events_recorded_at_now BEFORE INSERT ON events
  FOR EACH ROW EXECUTE FUNCTION events_recorded_at_now();
"""

DROP_RECORDED_AT_NOW = """
DROP TRIGGER events_recorded_at_now ON events;
DROP FUNCTION events_recorded_at_now();
"""

RULES = [
    db_rules.two_column_link(
        "event_void_same_batch",
        "events",
        "voids_event_id, batch_id",
        "events",
        "id, batch_id",
    ),
    db_rules.two_column_link(
        "event_correction_same_batch",
        "events",
        "corrects_event_id, batch_id",
        "events",
        "id, batch_id",
    ),
    *(
        db_rules.append_only(table)
        for table in ["events", "operations", "event_reviews"]
    ),
]


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0001_initial"),
        ("core", "0002_protection_functions"),
    ]

    operations = [
        migrations.RunSQL(RECORDED_AT_NOW, DROP_RECORDED_AT_NOW),
        *(migrations.RunSQL(rule.forward, rule.reverse) for rule in RULES),
    ]
