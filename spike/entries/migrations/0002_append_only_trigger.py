"""Make entries append-only at the database level.

Even raw SQL or the Django admin can't change or delete a saved entry.
This is the spike's version of the U0.2 rule "events can't be edited".
"""

from django.db import migrations

CREATE_TRIGGER = """
CREATE FUNCTION entries_refuse_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'entries are append-only: % refused', TG_OP;
END;
$$;

CREATE TRIGGER entries_append_only
BEFORE UPDATE OR DELETE ON entries_entry
FOR EACH ROW EXECUTE FUNCTION entries_refuse_change();
"""

DROP_TRIGGER = """
DROP TRIGGER IF EXISTS entries_append_only ON entries_entry;
DROP FUNCTION IF EXISTS entries_refuse_change();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("entries", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_TRIGGER, reverse_sql=DROP_TRIGGER),
    ]
