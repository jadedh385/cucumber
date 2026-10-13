"""`manage.py cucumber_flag`: list flags or switch one, with fixed meanings.

    cucumber_flag list
    cucumber_flag <name> on              on for everyone, groups cleared
    cucumber_flag <name> off             off for everyone, groups cleared
    cucumber_flag <name> on --group Owner [--group Lab]
                                         on for those groups only

Waffle's other switches (superusers, staff, percentage, ...) are always off.
Flags are created by the feature's migration; an unknown name is refused, so
a typo can't create one (U0.4a design §7). Runs as `cucumber_app`.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser


class Command(BaseCommand):
    help = "List feature flags, or switch one on or off."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("name", help='a flag name, or "list"')
        parser.add_argument("state", nargs="?", choices=["on", "off"])
        parser.add_argument(
            "--group",
            action="append",
            default=[],
            help="with on: only for this group (repeat for more)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        raise NotImplementedError("U0.4a G3")
