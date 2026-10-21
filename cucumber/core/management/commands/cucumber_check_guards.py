"""`manage.py cucumber_check_guards`: are the database's protections on? (AC15).

    cucumber_check_guards                      check; exit 1 if any is off
    cucumber_check_guards --accept "why"       list the noticed TRUNCATEs, ask, accept

Prints one line per protection that is missing, switched off or changed,
then stops with an error (exit 1); with none, prints `All N protections on.`
The deploy runs it before the copy and after migrating (U0.7 design §8.3).
`--accept` runs as the database owner, through the migrate service (§8.2); it
accepts exactly the TRUNCATEs it listed, once you type yes (`--yes` skips the
question). Any other login is refused.
"""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from cucumber.core import guards


class Command(BaseCommand):
    help = "Check the database's protections are on; --accept a noticed TRUNCATE."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--accept",
            metavar="WHY",
            help="accept the TRUNCATEs listed, saying why (asks first)",
        )
        parser.add_argument(
            "--yes", action="store_true", help="with --accept: don't ask first"
        )

    def handle(self, *args: Any, **options: Any) -> None:
        note: str | None = options["accept"]
        if note is not None:
            self.accept(note, options["yes"])
            return
        report = guards.check()
        if report.failures:
            for failure in report.failures:
                self.stdout.write(failure)
            raise CommandError(
                f"{len(report.failures)} of the database's protections are not on."
            )
        self.stdout.write(f"All {report.checked} protections on.")

    def accept(self, note: str, assume_yes: bool) -> None:
        """List what was truncated, ask, then accept exactly what was listed."""
        try:
            guards.require_owner()
            if not note.strip():
                raise ValueError("Say why the truncates are accepted.")
            noticed = guards.noticed_truncates()
            if not noticed:
                self.stdout.write("Nothing to accept.")
                return
            lines = [f"{table} ({when})" for _, table, when in noticed]
            self.stdout.write(f"These were truncated: {', '.join(lines)}")
            if not (assume_yes or self.confirmed()):
                self.stdout.write("Nothing accepted.")
                return
            guards.accept_truncates(note, [row_id for row_id, _, _ in noticed])
        except ValueError as error:
            raise CommandError(str(error)) from None
        self.stdout.write("Accepted. The deploy will go on.")

    def confirmed(self) -> bool:
        """Typed yes; no keyboard (e.g. run from a script) counts as no."""
        try:
            answer = input("Accept these? Type yes to go on: ")
        except EOFError:
            return False
        return answer.strip().lower() == "yes"
