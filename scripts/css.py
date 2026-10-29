"""Build Cucumber's one stylesheet with the pinned Tailwind CLI (U0.10a §3.3).

    uv run python -m scripts.css fetch    # download the CLI for this machine
    uv run python -m scripts.css build    # fetch, then compile cucumber.css
    uv run python -m scripts.css watch    # the same, rebuilding on each change

No Node: Tailwind's standalone CLI, checked against its SHA-256 before it is
used, with daisyUI's committed plugin files. The CLI is kept in
`$CUCUMBER_TOOLS` (default `.cache/tools/`), never in git or the image.
Standard library only, like the other server scripts.
"""

import argparse
import hashlib
import os
import platform as host
import shutil
import stat
import subprocess
import sys
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "cucumber/core/css/source.css"
OUTPUT = ROOT / "cucumber/core/static/core/cucumber.css"
TOOLS_VARIABLE = "CUCUMBER_TOOLS"
DEFAULT_TOOLS = ROOT / ".cache/tools"

DOWNLOAD_TIMEOUT_S = 120  # the CLI is about 100 MB
HASH_CHUNK_BYTES = 1024 * 1024

# The one place the Tailwind CLI's version, address and hashes live (§3.1):
# the latest 4.3.x patch at least two weeks old at G3 (2026-10-29), with the
# SHA-256 GitHub publishes for each release file. Checked by hand at each
# phase release gate (§19).
TAILWIND_VERSION = "4.3.3"
DOWNLOAD_URL = (
    "https://github.com/tailwindlabs/tailwindcss/releases/download/"
    "v{version}/tailwindcss-{platform}"
)
PLACEHOLDER_SHA256 = "0" * 64
CHECKSUMS: dict[str, str] = {
    "linux-x64": "dc61b3ac6b8c9ca874c0cc4c57b2409791a64c5540404ca5f5367360babc313a",
    "linux-arm64": "55fd0b241214eff3de1e8ee4f22796662f2d2e7a49bcfca7477cfd0bac398195",
    "macos-arm64": "cdf646702987a743464dff4d9c60fd4480d1c1e73dd819a9a67f1078815dce9d",
    "macos-x64": "7922e0953f2110c05976e3bf58f14e643d90427575e766b7d433f5f80cbee7e1",
}
# (platform.system(), platform.machine()) → the release's platform name.
PLATFORMS: dict[tuple[str, str], str] = {
    ("Linux", "x86_64"): "linux-x64",
    ("Linux", "aarch64"): "linux-arm64",
    ("Linux", "arm64"): "linux-arm64",
    ("Darwin", "arm64"): "macos-arm64",
    ("Darwin", "x86_64"): "macos-x64",
}

Download = Callable[[str, Path], None]  # (address, where to write it)
Run = Callable[[Sequence[str]], int]  # a command → its exit code


class CssError(Exception):
    """The CSS can't be built; the message says why."""


@dataclass(frozen=True)
class CssTools:
    """What the commands use from outside, so tests can give fakes."""

    download: Download
    run: Run
    system: str
    machine: str
    environ: Mapping[str, str]


def real_tools() -> CssTools:
    return CssTools(
        download=download_file,
        run=run_command,
        system=host.system(),
        machine=host.machine(),
        environ=os.environ,
    )


def download_file(address: str, to: Path) -> None:
    """Write what `address` answers into `to` (GitHub redirects are followed).

    Written beside `to` first and moved in whole, so a download cut off part
    way leaves nothing, and a CLI another run is using is never half a file.
    """
    if not address.startswith("https://"):
        raise CssError(f"only https:// downloads are allowed, not {address}")
    part = to.with_name(f"{to.name}.part")
    try:
        with urllib.request.urlopen(address, timeout=DOWNLOAD_TIMEOUT_S) as answer:  # noqa: S310 (scheme checked above)
            with part.open("wb") as file:
                shutil.copyfileobj(answer, file)
        os.replace(part, to)
    finally:
        part.unlink(missing_ok=True)


def run_command(command: Sequence[str]) -> int:
    return subprocess.run(command, check=False).returncode


def platform_name(system: str, machine: str) -> str:
    """The release's name for this machine; `CssError` for one with no CLI."""
    try:
        return PLATFORMS[(system, machine)]
    except KeyError:
        raise CssError(f"Tailwind has no CLI for {system} {machine}") from None


def tools_dir(environ: Mapping[str, str]) -> Path:
    """`$CUCUMBER_TOOLS`, or `.cache/tools/` in the repo."""
    named = environ.get(TOOLS_VARIABLE)
    return Path(named) if named else DEFAULT_TOOLS


def cli_path(tools: Path, platform: str) -> Path:
    """Where the pinned CLI for `platform` is kept: one file per version."""
    return tools / f"tailwindcss-{TAILWIND_VERSION}-{platform}"


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(tools: Path, platform: str, download: Download) -> Path:
    """The checked CLI, downloaded unless a copy with the right hash is there.

    A download whose SHA-256 differs from `CHECKSUMS` is deleted and refused
    with `CssError`; a cached copy that differs is downloaded again.
    """
    expected = CHECKSUMS[platform]
    cli = cli_path(tools, platform)
    if not (cli.is_file() and sha256_of(cli) == expected):
        tools.mkdir(parents=True, exist_ok=True)
        download(DOWNLOAD_URL.format(version=TAILWIND_VERSION, platform=platform), cli)
        actual = sha256_of(cli)
        if actual != expected:
            cli.unlink()
            raise CssError(
                f"the Tailwind CLI for {platform} has the wrong SHA-256: "
                f"expected {expected}, got {actual}. Nothing was kept."
            )
    cli.chmod(cli.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return cli


def build_command(cli: Path, watch: bool = False) -> list[str]:
    """`tailwindcss -i source.css -o cucumber.css --minify` (`--watch` too)."""
    command = [str(cli), "-i", str(SOURCE), "-o", str(OUTPUT), "--minify"]
    return [*command, "--watch"] if watch else command


def main(argv: Sequence[str] | None = None, tools: CssTools | None = None) -> int:
    """`fetch`, `build` or `watch`; 0 on success, 1 with the reason on stderr."""
    parser = argparse.ArgumentParser(prog="python -m scripts.css")
    parser.add_argument("command", choices=["fetch", "build", "watch"])
    command = parser.parse_args(argv).command
    tools = tools or real_tools()
    try:
        name = platform_name(tools.system, tools.machine)
        cli = fetch(tools_dir(tools.environ), name, tools.download)
    except (CssError, OSError) as error:
        print(f"css: {error}", file=sys.stderr)
        return 1
    if command == "fetch":
        return 0
    code = tools.run(build_command(cli, watch=command == "watch"))
    if code != 0:
        print(f"css: Tailwind stopped with exit code {code}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
