"""`manage.py cucumber_flag`: list flags or switch one, with fixed meanings.

    cucumber_flag list
    cucumber_flag <name> on              on for everyone, groups cleared
    cucumber_flag <name> off             off for everyone, groups cleared
    cucumber_flag <name> on --group Owner [--group Lab]
                                         on for those groups only

Waffle's other switches (superusers, staff, percentage, ...) are always off.
Flags are created by the feature's migration; an unknown name is refused, so
a typo can't create one (U0.4a design §7). Runs as `cucumber_app`; each
switch is an audit row by System (U0.7 AC6, AC10).
"""

from typing import Any

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError, CommandParser
from waffle.models import Flag

from cucumber.core.audit import SYSTEM, audited

# Waffle's switches other than `everyone` and groups, each in its off state.
ALWAYS_OFF = {
    "superusers": False,
    "staff": False,
    "authenticated": False,
    "testing": False,
    "rollout": False,
    "percent": None,
    "languages": "",
}


def describe(flag: Any) -> str:
    """`on`, `off`, or `on for: Lab, Owner`."""
    if flag.everyone is not None:
        return "on" if flag.everyone else "off"
    groups = sorted(group.name for group in flag.groups.all())
    return f"on for: {', '.join(groups)}" if groups else "off"


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
        name: str = options["name"]
        state: str | None = options["state"]
        group_names: list[str] = options["group"]
        if name == "list":
            self.list_flags()
            return
        if state is None:
            raise CommandError(f"Say on or off, e.g. cucumber_flag {name} on")
        if state == "off" and group_names:
            raise CommandError("off is for everyone; --group goes with on only.")
        flag = self.find_flag(name)
        groups = self.find_groups(group_names)
        with audited(SYSTEM, via="cucumber_flag"):
            for field, off in ALWAYS_OFF.items():
                setattr(flag, field, off)
            flag.everyone = None if groups else state == "on"
            flag.save()
            flag.groups.set(groups)
        self.stdout.write(f"{name} is now {describe(flag)}")

    def list_flags(self) -> None:
        self.stdout.write(f"Flags on {settings.ENVIRONMENT}")
        for flag in Flag.objects.order_by("name"):
            self.stdout.write(f"  {flag.name:<20} {describe(flag)}")

    def find_flag(self, name: str) -> Any:
        flag = Flag.objects.filter(name=name).first()
        if flag is None:
            names = ", ".join(
                Flag.objects.order_by("name").values_list("name", flat=True)
            )
            raise CommandError(
                f"No flag called {name}. "
                f"Flags on {settings.ENVIRONMENT}: {names or '(none yet)'}"
            )
        return flag

    def find_groups(self, names: list[str]) -> list[Group]:
        groups = list(Group.objects.filter(name__in=names))
        missing = sorted(set(names) - {group.name for group in groups})
        if missing:
            raise CommandError(f"No group called {', '.join(missing)}.")
        return groups
