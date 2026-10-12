"""Plant rules Django can't declare (design §2.2, §4).

- The SKU must be one issued to this plant: `(sku, id)` → `skus (sku, plant_id)`.
- Static SKU (Q1): never cleared; changed only together with the genus.
- Plants are never deleted; the SKU register and status history are insert-only.
"""

from django.db import migrations

from cucumber.core import db_rules

SKU_STATIC = """
CREATE FUNCTION plant_sku_static() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.sku IS NOT NULL AND NEW.sku IS DISTINCT FROM OLD.sku
     AND (NEW.sku IS NULL OR NEW.genus_code = OLD.genus_code) THEN
    RAISE EXCEPTION 'SKU % can''t be cleared, or changed without a genus change',
      OLD.sku
      USING ERRCODE = 'restrict_violation', CONSTRAINT = 'plant_sku_static';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER plant_sku_static BEFORE UPDATE ON plants
  FOR EACH ROW EXECUTE FUNCTION plant_sku_static();
"""

DROP_SKU_STATIC = """
DROP TRIGGER plant_sku_static ON plants;
DROP FUNCTION plant_sku_static();
"""

RULES = [
    db_rules.two_column_link(
        "plant_sku_belongs_to_plant", "plants", "sku, id", "skus", "sku, plant_id"
    ),
    db_rules.no_delete("plants"),
    db_rules.append_only("skus"),
    db_rules.append_only("plant_status_changes"),
]


class Migration(migrations.Migration):
    dependencies = [
        ("plants", "0001_initial"),
        ("core", "0002_protection_functions"),
    ]

    operations = [
        migrations.RunSQL(SKU_STATIC, DROP_SKU_STATIC),
        *(migrations.RunSQL(rule.forward, rule.reverse) for rule in RULES),
    ]
