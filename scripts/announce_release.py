"""Post a published release's "For staff" part to Discord (U0.4a design §8, AC14).

Run by `.github/workflows/announce-release.yml` on `release: published`. The
release text comes from the event file GitHub provides (`GITHUB_EVENT_PATH`),
the webhook from the `DISCORD_RELEASE_WEBHOOK` secret, whose address is never
printed. Mentions are switched off, so a note can't ping anyone.
"""

import json
import os
import re
import time
from collections.abc import Callable, Mapping

from scripts.staff_notes import NO_NOTES
from scripts.web import request

DISCORD_LIMIT = 2000
# Discord's "too many requests" says how long to wait; longer than this, or no
# usable answer, and the run fails instead (the Owner posts by hand).
MAX_RETRY_WAIT_SECONDS = 60
TOO_MANY_REQUESTS = 429
USER_AGENT = "Cucumber release announcer (https://github.com/jadedh385/cucumber)"
STAFF_HEADING = re.compile(r"##\s+for staff\s*", re.IGNORECASE)
NEXT_SECTION = re.compile(r"#{1,2}\s")
NOTHING_FOR_STAFF = {"", "none", "none.", NO_NOTES.lower()}
BY_HAND = "The release is published; post the staff note in Discord by hand."

# url, body, headers -> (status, body)
Post = Callable[[str, bytes, Mapping[str, str]], tuple[int, str]]


def staff_section(body: str) -> str | None:
    """The text under `## For staff`; None if missing, empty or "None"."""
    lines = body.replace("\r\n", "\n").split("\n")
    starts = [
        i for i, line in enumerate(lines) if STAFF_HEADING.fullmatch(line.strip())
    ]
    if not starts:
        return None
    section = lines[starts[0] + 1 :]
    ends = [i for i, line in enumerate(section) if NEXT_SECTION.match(line)]
    text = "\n".join(section[: ends[0]] if ends else section).strip()
    return None if text.lower() in NOTHING_FOR_STAFF else text


def build_message(version: str, section: str, release_url: str) -> str:
    """Heading plus the note, cut to fit one Discord message with a link."""
    heading = f"**Cucumber {version} is live**\n\n"
    if len(heading) + len(section) <= DISCORD_LIMIT:
        return heading + section
    link = f"\n\nFull notes: {release_url}"
    room = DISCORD_LIMIT - len(heading) - len(link)
    kept: list[str] = []
    for line in section.split("\n"):
        if len("\n".join([*kept, line])) > room:
            break
        kept.append(line)
    note = "\n".join(kept) if kept else section[:room]  # one very long line
    return heading + note.rstrip() + link


def retry_wait(answer: str) -> float | None:
    """Seconds Discord asked to wait, if usable and short enough."""
    try:
        wait = json.loads(answer).get("retry_after")
    except (json.JSONDecodeError, AttributeError):
        return None
    usable = isinstance(wait, int | float) and not isinstance(wait, bool)
    return float(wait) if usable and 0 <= wait <= MAX_RETRY_WAIT_SECONDS else None


def send(
    post: Post, webhook: str, message: str, sleep: Callable[[float], None]
) -> tuple[int, str]:
    """Post once; on "too many requests", wait as asked and try once more."""
    body = json.dumps({"content": message, "allowed_mentions": {"parse": []}})
    headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
    status, answer = post(webhook, body.encode(), headers)
    if status != TOO_MANY_REQUESTS:
        return status, answer
    wait = retry_wait(answer)
    if wait is None:
        return status, answer
    sleep(wait)
    return post(webhook, body.encode(), headers)


def read_release(os_environ: Mapping[str, str]) -> dict[str, object]:
    with open(os_environ["GITHUB_EVENT_PATH"]) as event:
        release = json.load(event)["release"]
    if not isinstance(release, dict):
        raise ValueError("the event has no release")
    return release


def main(
    os_environ: Mapping[str, str],
    post: Post,
    sleep: Callable[[float], None],
    say: Callable[[str], None],
) -> int:
    """Post the note; 0 when posted or nothing to post, 1 when it failed."""
    release = read_release(os_environ)
    version = str(release["tag_name"])
    if release.get("draft"):
        say(f"{version} is a draft, so nothing was posted.")
        return 0
    section = staff_section(str(release.get("body") or ""))
    if section is None:
        say(f"Nothing for staff in {version}, so nothing was posted.")
        return 0
    webhook = os_environ.get("DISCORD_RELEASE_WEBHOOK", "").strip()
    if not webhook:
        say(f"The DISCORD_RELEASE_WEBHOOK secret is not set. {BY_HAND}")
        return 1
    message = build_message(version, section, str(release["html_url"]))
    try:
        status, _ = send(post, webhook, message, sleep)
    except OSError as error:
        # The error text can hold the webhook address, so only its kind is shown.
        say(f"Couldn't reach Discord ({type(error).__name__}). {BY_HAND}")
        return 1
    if not 200 <= status < 300:
        say(f"Discord refused the post (HTTP {status}). {BY_HAND}")
        return 1
    say(f"Posted the staff note for {version} to Discord.")
    return 0


def post_json(url: str, body: bytes, headers: Mapping[str, str]) -> tuple[int, str]:
    return request(url, headers, data=body)


if __name__ == "__main__":
    raise SystemExit(main(os.environ, post_json, time.sleep, print))
