"""U0.10a AC1: the stylesheet is built by the pinned, checked Tailwind CLI (§3.3).

Downloads are faked: each test gives `fetch` a function that writes bytes
where the real download would, and the checksums are set to match (or not).
"""

import hashlib
import re
import stat
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts import css
from scripts.css import CssError, CssTools

CLI_BYTES = b"#!/bin/sh\necho tailwind\n"
CLI_SHA256 = hashlib.sha256(CLI_BYTES).hexdigest()
OTHER_BYTES = b"#!/bin/sh\necho something else\n"


class FakeDownload:
    """Writes `content` at the given path and remembers each address asked for."""

    def __init__(self, content: bytes = CLI_BYTES) -> None:
        self.content = content
        self.addresses: list[str] = []

    def __call__(self, address: str, to: Path) -> None:
        self.addresses.append(address)
        to.write_bytes(self.content)


class FakeRun:
    """Remembers each command; answers with `code`."""

    def __init__(self, code: int = 0) -> None:
        self.code = code
        self.commands: list[list[str]] = []

    def __call__(self, command: Sequence[str]) -> int:
        self.commands.append(list(command))
        return self.code


@pytest.fixture
def pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every platform's checksum is the fake CLI's."""
    monkeypatch.setattr(css, "CHECKSUMS", dict.fromkeys(css.CHECKSUMS, CLI_SHA256))


def fake_tools(
    tmp_path: Path, download: FakeDownload | None = None, run: FakeRun | None = None
) -> CssTools:
    """An Apple-silicon Mac whose tools folder is under `tmp_path`."""
    return CssTools(
        download=download or FakeDownload(),
        run=run or FakeRun(),
        system="Darwin",
        machine="arm64",
        environ={css.TOOLS_VARIABLE: str(tmp_path / "tools")},
    )


# ------------------------------------------------------- versions and hashes
def test_every_platform_has_a_pinned_checksum() -> None:
    """G3 replaces the placeholders with the release's real hashes (§3.1)."""
    assert set(css.CHECKSUMS) == {
        "linux-x64",
        "linux-arm64",
        "macos-arm64",
        "macos-x64",
    }
    for platform, checksum in css.CHECKSUMS.items():
        assert re.fullmatch(r"[0-9a-f]{64}", checksum), platform
        assert checksum != css.PLACEHOLDER_SHA256, f"{platform} is not pinned yet"


def test_the_version_is_a_tailwind_4_release() -> None:
    assert re.fullmatch(r"4\.\d+\.\d+", css.TAILWIND_VERSION)


@pytest.mark.parametrize(
    ("system", "machine", "platform"),
    [
        ("Linux", "x86_64", "linux-x64"),
        ("Linux", "aarch64", "linux-arm64"),
        ("Linux", "arm64", "linux-arm64"),
        ("Darwin", "arm64", "macos-arm64"),
        ("Darwin", "x86_64", "macos-x64"),
    ],
)
def test_each_machine_gets_its_own_cli(
    system: str, machine: str, platform: str
) -> None:
    assert css.platform_name(system, machine) == platform


@pytest.mark.parametrize(
    ("system", "machine"), [("Windows", "AMD64"), ("Linux", "armv7l")]
)
def test_a_machine_with_no_cli_is_refused_by_name(system: str, machine: str) -> None:
    with pytest.raises(CssError, match=f"{system} {machine}"):
        css.platform_name(system, machine)


# ---------------------------------------------------------- where it is kept
def test_the_cli_is_kept_in_the_tools_folder_named() -> None:
    assert css.tools_dir({css.TOOLS_VARIABLE: "/opt/tools"}) == Path("/opt/tools")


def test_by_default_it_is_kept_in_the_repos_cache_folder() -> None:
    assert css.tools_dir({}) == css.ROOT / ".cache" / "tools"


def test_each_version_and_platform_has_its_own_file(tmp_path: Path) -> None:
    path = css.cli_path(tmp_path, "linux-x64")

    assert path.parent == tmp_path
    assert css.TAILWIND_VERSION in path.name
    assert "linux-x64" in path.name


def test_the_cache_folder_is_never_committed() -> None:
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", ".cache/tools/tailwindcss"],
        cwd=css.ROOT,
        check=False,
    )
    assert ignored.returncode == 0


# ------------------------------------------------------------------- fetch
@pytest.mark.usefixtures("pinned")
def test_fetch_downloads_the_pinned_release_for_the_platform(tmp_path: Path) -> None:
    download = FakeDownload()

    cli = css.fetch(tmp_path, "linux-arm64", download)

    assert download.addresses == [
        "https://github.com/tailwindlabs/tailwindcss/releases/download/"
        f"v{css.TAILWIND_VERSION}/tailwindcss-linux-arm64"
    ]
    assert cli == css.cli_path(tmp_path, "linux-arm64")
    assert cli.read_bytes() == CLI_BYTES


@pytest.mark.usefixtures("pinned")
def test_the_fetched_cli_can_be_run(tmp_path: Path) -> None:
    cli = css.fetch(tmp_path, "macos-arm64", FakeDownload())

    assert cli.stat().st_mode & stat.S_IXUSR


@pytest.mark.usefixtures("pinned")
def test_the_tools_folder_is_made_if_missing(tmp_path: Path) -> None:
    cli = css.fetch(tmp_path / "a" / "b", "linux-x64", FakeDownload())

    assert cli.is_file()


@pytest.mark.usefixtures("pinned")
def test_a_download_with_another_hash_is_refused_and_deleted(tmp_path: Path) -> None:
    with pytest.raises(CssError, match="linux-x64") as refused:
        css.fetch(tmp_path, "linux-x64", FakeDownload(OTHER_BYTES))

    assert CLI_SHA256 in str(refused.value)
    assert hashlib.sha256(OTHER_BYTES).hexdigest() in str(refused.value)
    assert list(tmp_path.iterdir()) == [], "the bad download must not be kept"


@pytest.mark.usefixtures("pinned")
def test_a_cached_cli_with_the_right_hash_is_not_downloaded_again(
    tmp_path: Path,
) -> None:
    css.fetch(tmp_path, "linux-x64", FakeDownload())
    again = FakeDownload()

    css.fetch(tmp_path, "linux-x64", again)

    assert again.addresses == []


@pytest.mark.usefixtures("pinned")
def test_a_cached_cli_with_a_wrong_hash_is_downloaded_again(tmp_path: Path) -> None:
    cli = css.cli_path(tmp_path, "linux-x64")
    cli.write_bytes(OTHER_BYTES)
    download = FakeDownload()

    css.fetch(tmp_path, "linux-x64", download)

    assert len(download.addresses) == 1
    assert cli.read_bytes() == CLI_BYTES


# ------------------------------------------------------------- build, watch
def test_build_compiles_the_one_source_into_the_served_stylesheet() -> None:
    cli = Path("/tools/tailwindcss")

    assert css.build_command(cli) == [
        str(cli),
        "-i",
        str(css.SOURCE),
        "-o",
        str(css.OUTPUT),
        "--minify",
    ]


def test_watch_is_the_same_command_with_watch() -> None:
    cli = Path("/tools/tailwindcss")

    assert css.build_command(cli, watch=True) == [*css.build_command(cli), "--watch"]


def test_the_stylesheet_keeps_its_address() -> None:
    """`{% static 'core/cucumber.css' %}` and the deploy rehearsal still find it."""
    assert css.OUTPUT == css.ROOT / "cucumber/core/static/core/cucumber.css"
    assert css.SOURCE == css.ROOT / "cucumber/core/css/source.css"


# ------------------------------------------------------------- the command
@pytest.mark.usefixtures("pinned")
def test_fetch_command_downloads_for_this_machine(tmp_path: Path) -> None:
    download = FakeDownload()

    assert css.main(["fetch"], fake_tools(tmp_path, download=download)) == 0
    assert download.addresses[0].endswith("tailwindcss-macos-arm64")
    assert css.cli_path(tmp_path / "tools", "macos-arm64").is_file()


@pytest.mark.usefixtures("pinned")
def test_build_command_fetches_then_builds(tmp_path: Path) -> None:
    run = FakeRun()

    assert css.main(["build"], fake_tools(tmp_path, run=run)) == 0
    cli = css.cli_path(tmp_path / "tools", "macos-arm64")
    assert run.commands == [css.build_command(cli)]


@pytest.mark.usefixtures("pinned")
def test_watch_command_runs_the_cli_with_watch(tmp_path: Path) -> None:
    run = FakeRun()

    assert css.main(["watch"], fake_tools(tmp_path, run=run)) == 0
    assert run.commands == [
        css.build_command(css.cli_path(tmp_path / "tools", "macos-arm64"), watch=True)
    ]


@pytest.mark.usefixtures("pinned")
def test_a_failed_build_fails_the_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert css.main(["build"], fake_tools(tmp_path, run=FakeRun(code=1))) == 1
    assert "tailwind" in capsys.readouterr().err.lower()


@pytest.mark.usefixtures("pinned")
def test_a_refused_download_fails_the_command_before_building(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run = FakeRun()
    tools = fake_tools(tmp_path, download=FakeDownload(OTHER_BYTES), run=run)

    assert css.main(["build"], tools) == 1
    assert run.commands == []
    assert "macos-arm64" in capsys.readouterr().err


@pytest.mark.parametrize(
    "address", ["http://github.com/tailwindlabs/tailwindcss", "file:///etc/passwd"]
)
def test_the_real_download_refuses_an_address_that_is_not_https(
    tmp_path: Path, address: str
) -> None:
    to = tmp_path / "tailwindcss"

    with pytest.raises(CssError, match="only https://"):
        css.download_file(address, to)
    assert not to.exists()


def test_an_unknown_command_is_a_usage_error(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as stop:
        css.main(["publish"], fake_tools(tmp_path))

    assert stop.value.code == 2
