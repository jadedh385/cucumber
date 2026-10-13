"""What the app user may do with feature flags (U0.4a design §7, AC6, AC13).

`cucumber_flag` and, later, the on-screen switch (U0.6) run as
`cucumber_app`. They may switch a flag and set its groups, never create or
delete a flag (flags are made by the feature's migration), and only read
Waffle's other tables. This replaces the SELECT, INSERT that U0.2a's default
privileges give every new table; undo puts those defaults back.
"""

from django.db import migrations

FLAG_TABLES = (
    "waffle_flag, waffle_flag_groups, waffle_flag_users, waffle_switch, waffle_sample"
)

# Table names are the constant above, never input.
GRANT = f"""
REVOKE ALL ON {FLAG_TABLES} FROM cucumber_app;
GRANT SELECT, UPDATE ON waffle_flag TO cucumber_app;
GRANT SELECT, INSERT, DELETE ON waffle_flag_groups TO cucumber_app;
GRANT SELECT ON waffle_flag_users, waffle_switch, waffle_sample TO cucumber_app;
"""

DEFAULTS = f"""
REVOKE ALL ON {FLAG_TABLES} FROM cucumber_app;
GRANT SELECT, INSERT ON {FLAG_TABLES} TO cucumber_app;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_refuse_reverse_with_data"),
        ("waffle", "0004_update_everyone_nullbooleanfield"),
    ]

    operations = [migrations.RunSQL(GRANT, DEFAULTS)]
