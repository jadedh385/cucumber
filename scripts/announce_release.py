"""Post a published release's "For staff" part to Discord (U0.4a design §8, AC14).

Run by `.github/workflows/announce-release.yml` on `release: published`. The
release text comes from the event file GitHub provides (`GITHUB_EVENT_PATH`),
the webhook from the `DISCORD_RELEASE_WEBHOOK` secret, whose address is never
printed. Mentions are switched off, so a note can't ping anyone.
"""

from collections.abc import Callable, Mapping

NOT_BUILT = "U0.4a G3"
DISCORD_LIMIT = 2000
USER_AGENT = "Cucumber release announcer (https://github.com/jadedh385/cucumber)"

# url, body, headers -> (status, body)
Post = Callable[[str, bytes, Mapping[str, str]], tuple[int, str]]


def staff_section(body: str) -> str | None:
    """The text under `## For staff`; None if missing, empty or "None"."""
    raise NotImplementedError(NOT_BUILT)


def build_message(version: str, section: str, release_url: str) -> str:
    """Heading plus the note, cut to fit one Discord message with a link."""
    raise NotImplementedError(NOT_BUILT)


def main(
    os_environ: Mapping[str, str],
    post: Post,
    sleep: Callable[[float], None],
    say: Callable[[str], None],
) -> int:
    """Post the note; 0 when posted or nothing to post, 1 when it failed."""
    raise NotImplementedError(NOT_BUILT)
