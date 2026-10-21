"""AC13: the Owner switches a flag on a server with one command (design §7).

What the switch does to Waffle's rows is tested with `cucumber_flag` itself
(cucumber/core/tests/test_cucumber_flag.py); this is the server side.
"""

from pathlib import Path

import pytest

from scripts.flag import main
from scripts.server import Place
from scripts.tests.fake_server import (
    PREVIOUS,
    SSH_CONNECTION,
    SSH_USER,
    STRAY_SHELL_PASSWORD,
    FakeServer,
    make_home,
    shell_environment,
)

LISTING = "Flags on production\n  needs_attention      on for: admin\n"


def flag(
    tmp_path: Path,
    server: FakeServer,
    *args: str,
    current: str | None = PREVIOUS,
    secrets_mode: int = 0o600,
) -> tuple[int, Place]:
    """Run the command; a usage error (argparse's exit) counts as its exit code."""
    home = make_home(tmp_path, "production", current=current, secrets_mode=secrets_mode)
    try:
        code = main(["production", *args], server.tools(), shell_environment(home))
    except SystemExit as stop:
        code = stop.code if isinstance(stop.code, int) else 1
    return code, Place("production", home)


def flags_log(place: Place) -> list[str]:
    path = place.logs / "flags.log"
    return path.read_text().splitlines() if path.exists() else []


def test_list_shows_what_the_app_reports(tmp_path: Path) -> None:
    server = FakeServer(flag_output=LISTING)

    code, place = flag(tmp_path, server, "list")

    assert code == 0
    assert "needs_attention      on for: admin" in server.output()
    assert server.first("flag").command[-1] == "list"
    assert flags_log(place) == []


def test_the_command_runs_inside_the_running_app(tmp_path: Path) -> None:
    server = FakeServer()

    flag(tmp_path, server, "list")

    call = server.first("flag")
    assert {"exec", "-T", "app", "manage.py"} <= set(call.command)
    assert call.command[call.command.index("-p") + 1] == "cucumber-production"
    assert call.env is not None
    assert call.env["CUCUMBER_VERSION"] == PREVIOUS
    assert call.env["IMAGE_NAME"] == "cucumber-production"
    assert "DB_PASSWORD" not in call.env
    assert STRAY_SHELL_PASSWORD not in call.env.values()


def test_who_and_from_where_go_into_the_app(tmp_path: Path) -> None:
    """G4 review #3: `cucumber_flag` records them in `via`."""
    server = FakeServer()

    flag(tmp_path, server, "list")

    command = server.first("flag").command
    assert f"SSH_USER={SSH_USER}" in command
    assert f"SSH_CONNECTION={SSH_CONNECTION}" in command
    assert command.index("-e") < command.index("app")


@pytest.mark.parametrize(
    "args",
    [
        ["needs_attention", "on"],
        ["needs_attention", "off"],
        ["needs_attention", "on", "--group", "admin", "--group", "supervisor"],
    ],
)
def test_a_switch_is_passed_to_the_app_as_given(
    tmp_path: Path, args: list[str]
) -> None:
    server = FakeServer()

    code, _ = flag(tmp_path, server, *args)

    assert code == 0, server.output()
    command = server.first("flag").command
    assert command[command.index("cucumber_flag") + 1 :] == args


def test_each_change_is_added_to_the_flags_log(tmp_path: Path) -> None:
    server = FakeServer()

    _, place = flag(tmp_path, server, "needs_attention", "on", "--group", "admin")
    second = main(
        ["production", "needs_attention", "off"],
        server.tools(),
        shell_environment(place.home),
    )

    assert second == 0
    lines = flags_log(place)
    assert len(lines) == 2
    assert lines[0].startswith("2026-10-13 14:0")  # Bangkok time
    assert "needs_attention" in lines[0] and " on" in lines[0]
    assert "admin" in lines[0]
    assert "needs_attention" in lines[1] and " off" in lines[1]


def test_a_refused_switch_is_shown_and_not_logged(tmp_path: Path) -> None:
    server = FakeServer(failing={"flag"})

    code, place = flag(tmp_path, server, "needs_atention", "on")

    assert code == 1
    assert "pretend flag error" in server.output()
    assert flags_log(place) == []


def test_nothing_deployed_yet_is_said_plainly(tmp_path: Path) -> None:
    server = FakeServer()

    code, _ = flag(tmp_path, server, "list", current=None)

    assert code == 1
    assert "Nothing is deployed on production yet" in server.output()
    assert server.calls == []


def test_secrets_readable_by_others_are_refused(tmp_path: Path) -> None:
    server = FakeServer()

    code, _ = flag(tmp_path, server, "list", secrets_mode=0o644)

    assert code == 1
    assert "chmod 600" in server.output()
    assert server.calls == []


def test_off_for_some_groups_is_refused(tmp_path: Path) -> None:
    """`off` always clears groups (design §7), so a group with off is a mistake."""
    server = FakeServer()

    code, _ = flag(tmp_path, server, "needs_attention", "off", "--group", "admin")

    assert code != 0
    assert server.calls == []


def test_a_flag_name_needs_on_or_off(tmp_path: Path) -> None:
    server = FakeServer()

    code, _ = flag(tmp_path, server, "needs_attention")

    assert code != 0
    assert server.calls == []
