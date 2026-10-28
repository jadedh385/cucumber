"""Build Cucumber's one stylesheet with the pinned Tailwind CLI (U0.10a §3.3).

    uv run python -m scripts.css fetch    # download the CLI for this machine
    uv run python -m scripts.css build    # fetch, then compile cucumber.css
    uv run python -m scripts.css watch    # the same, rebuilding on each change

No Node: Tailwind's standalone CLI, checked against its SHA-256 before it is
used, with daisyUI's committed plugin files. The CLI is kept in
`$CUCUMBER_TOOLS` (default `.cache/tools/`), never in git or the image.
Standard library only, like the other server scripts. G2 stub: the
constants are the contract; the behaviour is built at G3.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "cucumber/core/css/source.css"
OUTPUT = ROOT / "cucumber/core/static/core/cucumber.css"
TOOLS_VARIABLE = "CUCUMBER_TOOLS"
DEFAULT_TOOLS = ROOT / ".cache/tools"

# The one place the Tailwind CLI's version, address and hashes live (§3.1).
# G3 pins the latest 4.3.x patch at least two weeks old and its hashes; until
# then the hashes are placeholders and nothing can be downloaded.
TAILWIND_VERSION = "4.3.3"
DOWNLOAD_URL = (
    "https://github.com/tailwindlabs/tailwindcss/releases/download/"
    "v{version}/tailwindcss-{platform}"
)
PLACEHOLDER_SHA256 = "0" * 64
CHECKSUMS: dict[str, str] = {
    "linux-x64": PLACEHOLDER_SHA256,
    "linux-arm64": PLACEHOLDER_SHA256,
    "macos-arm64": PLACEHOLDER_SHA256,
    "macos-x64": PLACEHOLDER_SHA256,
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
    raise NotImplementedError("U0.10a G3")


def platform_name(system: str, machine: str) -> str:
    """The release's name for this machine; `CssError` for one with no CLI."""
    raise NotImplementedError("U0.10a G3")


def tools_dir(environ: Mapping[str, str]) -> Path:
    """`$CUCUMBER_TOOLS`, or `.cache/tools/` in the repo."""
    raise NotImplementedError("U0.10a G3")


def cli_path(tools: Path, platform: str) -> Path:
    """Where the pinned CLI for `platform` is kept: one file per version."""
    raise NotImplementedError("U0.10a G3")


def fetch(tools: Path, platform: str, download: Download) -> Path:
    """The checked CLI, downloaded unless a copy with the right hash is there.

    A download whose SHA-256 differs from `CHECKSUMS` is deleted and refused
    with `CssError`; a cached copy that differs is downloaded again.
    """
    raise NotImplementedError("U0.10a G3")


def build_command(cli: Path, watch: bool = False) -> list[str]:
    """`tailwindcss -i source.css -o cucumber.css --minify` (`--watch` too)."""
    raise NotImplementedError("U0.10a G3")


def main(argv: Sequence[str] | None = None, tools: CssTools | None = None) -> int:
    """`fetch`, `build` or `watch`; 0 on success, 1 with the reason on stderr."""
    raise NotImplementedError("U0.10a G3")


if __name__ == "__main__":
    raise SystemExit(main())
