"""Switch a feature flag on a server (U0.4a design §7, AC13).

    uv run --no-dev python -m scripts.flag production list
    uv run --no-dev python -m scripts.flag production needs_attention on
    uv run --no-dev python -m scripts.flag production needs_attention on --group admin
    uv run --no-dev python -m scripts.flag production needs_attention off

Runs `manage.py cucumber_flag` inside the environment's running app, as
`cucumber_app`, and adds each change to `logs/flags.log`.
"""

import argparse
import os
from collections.abc import Mapping, Sequence

from scripts.next_version import BANGKOK
from scripts.server import (
    Place,
    ServerError,
    Tools,
    check_secrets_private,
    compose_command,
    compose_environment,
    current_version,
    place_for,
    real_tools,
)


def parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.flag",
        description="List feature flags on a server, or switch one on or off.",
    )
    parser.add_argument("environment", help="staging or production")
    parser.add_argument("name", help='a flag name, or "list"')
    parser.add_argument("state", nargs="?", choices=["on", "off"])
    parser.add_argument(
        "--group",
        action="append",
        default=[],
        help="with on: only for this group (repeat for more)",
    )
    args = parser.parse_args(argv)
    if args.name != "list" and args.state is None:
        parser.error(f"say on or off, e.g. {args.name} on")
    if args.state == "off" and args.group:
        parser.error("off is for everyone; --group goes with on only")
    return args


def flag_arguments(args: argparse.Namespace) -> list[str]:
    """What to pass on to `manage.py cucumber_flag`, in the order given."""
    groups = [part for group in args.group for part in ("--group", group)]
    return [args.name, *([args.state] if args.state else []), *groups]


def log_change(place: Place, tools: Tools, args: argparse.Namespace) -> None:
    """Add one line to `logs/flags.log` (design §7, G6 evidence)."""
    when = f"{tools.now().astimezone(BANGKOK):%Y-%m-%d %H:%M:%S}"
    groups = f" for: {', '.join(args.group)}" if args.group else ""
    place.logs.mkdir(exist_ok=True)
    with (place.logs / "flags.log").open("a") as log:
        log.write(f"{when}  {args.name} {args.state}{groups}\n")


def run_flag(
    place: Place, tools: Tools, shell: Mapping[str, str], args: argparse.Namespace
) -> int:
    check_secrets_private(place)
    version = current_version(place)
    if version is None:
        raise ServerError(
            f"Nothing is deployed on {place.environment} yet, so there are no flags."
        )
    command = compose_command(
        place, "exec", "-T", "app", "python", "manage.py", "cucumber_flag",
        *flag_arguments(args),
    )  # fmt: skip
    env = compose_environment(shell, CUCUMBER_VERSION=version, IMAGE_NAME=place.image)
    try:
        output = tools.run(command, env)
    except RuntimeError as error:
        tools.say(str(error))
        return 1
    for line in output.splitlines():
        tools.say(line)
    if args.name != "list":
        log_change(place, tools, args)
    return 0


def main(
    argv: Sequence[str] | None = None,
    tools: Tools | None = None,
    os_environ: Mapping[str, str] | None = None,
) -> int:
    """Run one flag command; 0 when it worked, 1 otherwise."""
    args = parse_arguments(argv)
    tools = tools or real_tools()
    shell = os.environ if os_environ is None else os_environ
    try:
        place = place_for(args.environment, shell)
        return run_flag(place, tools, shell, args)
    except ServerError as error:
        tools.say(f"Stopped: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
