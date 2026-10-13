"""Switch a feature flag on a server (U0.4a design §7, AC13).

    uv run --no-dev python -m scripts.flag production list
    uv run --no-dev python -m scripts.flag production needs_attention on
    uv run --no-dev python -m scripts.flag production needs_attention on --group Owner
    uv run --no-dev python -m scripts.flag production needs_attention off

Runs `manage.py cucumber_flag` inside the environment's running app, as
`cucumber_app`, and adds each change to `logs/flags.log`.
"""

from collections.abc import Mapping, Sequence

from scripts.server import NOT_BUILT, Tools


def main(
    argv: Sequence[str] | None = None,
    tools: Tools | None = None,
    os_environ: Mapping[str, str] | None = None,
) -> int:
    """Run one flag command; 0 when it worked, 1 otherwise."""
    raise NotImplementedError(NOT_BUILT)


if __name__ == "__main__":
    raise SystemExit(main())
