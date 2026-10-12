"""What the app user, `cucumber_app`, may do: exactly design §4 (H3).

Runs after every table exists. New tables and sequences made by the owner
later get SELECT, INSERT (and USAGE, SELECT) by default; a migration that
adds a table needing more grants it in the same migration. TRUNCATE is
granted on nothing. `django_admin_log` is granted when the admin is added.
"""

from django.db import migrations

INSERT_ONLY = "events, operations, event_reviews, plant_status_changes, skus, audit_log"
NO_DELETE = "plants, batches, genera, stages, media_codes, locations, reasons, vendors"
HOUSEKEEPING = "django_session, auth_user_groups, auth_user_user_permissions"
READ_ONLY = (
    "auth_group, auth_permission, auth_group_permissions, django_content_type,"
    " django_migrations"
)
ALL_TABLES = ", ".join([INSERT_ONLY, NO_DELETE, HOUSEKEEPING, READ_ONLY, "auth_user"])

# Table lists are the constants above, never input.
GRANT = f"""
GRANT SELECT, INSERT ON {INSERT_ONLY} TO cucumber_app;
GRANT SELECT, INSERT, UPDATE ON {NO_DELETE} TO cucumber_app;
GRANT SELECT, INSERT, UPDATE ON auth_user TO cucumber_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON {HOUSEKEEPING} TO cucumber_app;
GRANT SELECT ON {READ_ONLY} TO cucumber_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO cucumber_app;
ALTER DEFAULT PRIVILEGES FOR ROLE cucumber_owner IN SCHEMA public
  GRANT SELECT, INSERT ON TABLES TO cucumber_app;
ALTER DEFAULT PRIVILEGES FOR ROLE cucumber_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO cucumber_app;
"""  # noqa: S608

REVOKE = f"""
ALTER DEFAULT PRIVILEGES FOR ROLE cucumber_owner IN SCHEMA public
  REVOKE USAGE, SELECT ON SEQUENCES FROM cucumber_app;
ALTER DEFAULT PRIVILEGES FOR ROLE cucumber_owner IN SCHEMA public
  REVOKE SELECT, INSERT ON TABLES FROM cucumber_app;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM cucumber_app;
REVOKE ALL ON {ALL_TABLES} FROM cucumber_app;
"""  # noqa: S608


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_protection_functions"),
        ("references", "0003_rules"),
        ("plants", "0002_rules"),
        ("batches", "0002_rules"),
        ("events", "0002_rules"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("sessions", "0001_initial"),
    ]

    operations = [migrations.RunSQL(GRANT, REVOKE)]
