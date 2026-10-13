"""AC14: publishing a release posts its "For staff" part to Discord (design §8)."""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from scripts.announce_release import (
    DISCORD_LIMIT,
    USER_AGENT,
    Post,
    build_message,
    main,
    staff_section,
)
from scripts.staff_notes import NO_NOTES

WEBHOOK = "https://discord.com/api/webhooks/123456/sentinel-webhook-token"
RELEASE_URL = "https://github.com/jadedh385/cucumber/releases/tag/2026.10.1"
STAFF_NOTE = "New\n- You can now split a batch for a pre-order."


def release_body(staff: str) -> str:
    """A release body shaped like the Draft release workflow makes it."""
    return f"## For staff\n\n{staff}\n\n## Technical changes\n### Added\n- split\n"


@dataclass
class FakeDiscord:
    """Answers posts in turn (the last answer repeats); records what was sent."""

    answers: list[tuple[int, str]] = field(default_factory=lambda: [(204, "")])
    posts: list[tuple[str, dict[str, object], dict[str, str]]] = field(
        default_factory=list
    )
    slept: list[float] = field(default_factory=list)
    said: list[str] = field(default_factory=list)

    def post(
        self, url: str, body: bytes, headers: Mapping[str, str]
    ) -> tuple[int, str]:
        self.posts.append((url, json.loads(body), dict(headers)))
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]

    def output(self) -> str:
        return "\n".join(self.said)


def announce(
    tmp_path: Path,
    discord: FakeDiscord,
    *,
    body: str | None = None,
    draft: bool = False,
    webhook: str | None = WEBHOOK,
    post: Post | None = None,
) -> int:
    release = {
        "tag_name": "2026.10.1",
        "body": release_body(STAFF_NOTE) if body is None else body,
        "html_url": RELEASE_URL,
        "draft": draft,
    }
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps({"action": "published", "release": release}))
    environment = {"GITHUB_EVENT_PATH": str(event_path)}
    if webhook is not None:
        environment["DISCORD_RELEASE_WEBHOOK"] = webhook
    return main(
        environment, post or discord.post, discord.slept.append, discord.said.append
    )


# ------------------------------------------------------------ the section
def test_the_staff_part_is_taken_and_the_technical_part_left_out() -> None:
    assert staff_section(release_body(STAFF_NOTE)) == STAFF_NOTE


def test_windows_line_endings_from_githubs_editor_are_understood() -> None:
    body = release_body(STAFF_NOTE).replace("\n", "\r\n")

    assert staff_section(body) == STAFF_NOTE


def test_smaller_headings_stay_inside_the_staff_part() -> None:
    staff = "### New\n- Split a batch.\n\n### Changed\n- Losses need a reason."

    assert staff_section(release_body(staff)) == staff


def test_the_staff_part_can_be_the_last_section() -> None:
    assert staff_section(f"## For staff\n\n{STAFF_NOTE}\n") == STAFF_NOTE


@pytest.mark.parametrize("staff", ["None", "none.", "", NO_NOTES])
def test_nothing_for_staff_means_no_section(staff: str) -> None:
    assert staff_section(release_body(staff)) is None


def test_a_release_without_the_section_has_none() -> None:
    assert staff_section("## Technical changes\n- fix\n") is None


# ------------------------------------------------------------ the message
def test_the_message_starts_with_the_version_in_bold() -> None:
    message = build_message("2026.10.1", STAFF_NOTE, RELEASE_URL)

    assert message == f"**Cucumber 2026.10.1 is live**\n\n{STAFF_NOTE}"


def test_a_long_note_is_cut_at_a_whole_line_with_a_link() -> None:
    lines = [f"- Change {number}: something staff will notice." for number in range(99)]

    message = build_message("2026.10.1", "\n".join(lines), RELEASE_URL)

    assert len(message) <= DISCORD_LIMIT
    assert message.endswith(f"Full notes: {RELEASE_URL}")
    note = message.split("\n\n", 1)[1].removesuffix(f"Full notes: {RELEASE_URL}")
    kept = note.strip().splitlines()
    assert kept and kept == lines[: len(kept)]


def test_a_single_very_long_line_is_cut_hard() -> None:
    message = build_message("2026.10.1", "x" * 5000, RELEASE_URL)

    assert len(message) <= DISCORD_LIMIT
    assert message.endswith(f"Full notes: {RELEASE_URL}")
    assert "x" * 100 in message


# -------------------------------------------------------------- posting
def test_the_note_is_posted_with_mentions_off_and_a_named_agent(
    tmp_path: Path,
) -> None:
    discord = FakeDiscord()

    code = announce(tmp_path, discord, body=release_body("Hi @everyone"))

    assert code == 0
    assert len(discord.posts) == 1
    url, sent, headers = discord.posts[0]
    assert url == WEBHOOK
    assert sent["content"] == "**Cucumber 2026.10.1 is live**\n\nHi @everyone"
    assert sent["allowed_mentions"] == {"parse": []}
    assert headers["User-Agent"] == USER_AGENT
    assert headers["Content-Type"] == "application/json"
    assert WEBHOOK not in discord.output()


def test_nothing_for_staff_posts_nothing_and_says_so(tmp_path: Path) -> None:
    discord = FakeDiscord()

    code = announce(tmp_path, discord, body=release_body("None"))

    assert code == 0
    assert discord.posts == []
    assert "nothing" in discord.output().lower()


def test_a_draft_is_never_announced(tmp_path: Path) -> None:
    discord = FakeDiscord()

    code = announce(tmp_path, discord, draft=True)

    assert code == 0
    assert discord.posts == []


def test_a_missing_webhook_secret_fails_with_a_plain_reason(tmp_path: Path) -> None:
    discord = FakeDiscord()

    code = announce(tmp_path, discord, webhook=None)

    assert code == 1
    assert "DISCORD_RELEASE_WEBHOOK" in discord.output()
    assert discord.posts == []


def test_too_many_requests_waits_as_asked_and_tries_once_more(
    tmp_path: Path,
) -> None:
    discord = FakeDiscord(answers=[(429, '{"retry_after": 1.5}'), (204, "")])

    code = announce(tmp_path, discord)

    assert code == 0
    assert len(discord.posts) == 2
    assert discord.slept == [1.5]


def test_too_many_requests_twice_fails(tmp_path: Path) -> None:
    discord = FakeDiscord(answers=[(429, '{"retry_after": 1}')])

    code = announce(tmp_path, discord)

    assert code == 1
    assert len(discord.posts) == 2


@pytest.mark.parametrize("status", [400, 401, 404, 500])
def test_a_discord_error_fails_the_run(tmp_path: Path, status: int) -> None:
    discord = FakeDiscord(answers=[(status, '{"message": "Unknown Webhook"}')])

    code = announce(tmp_path, discord)

    assert code == 1
    assert str(status) in discord.output()
    assert WEBHOOK not in discord.output()


def test_the_webhook_address_is_never_printed_even_in_an_error(
    tmp_path: Path,
) -> None:
    def unreachable(
        url: str, body: bytes, headers: Mapping[str, str]
    ) -> tuple[int, str]:
        raise OSError(f"could not reach {url}")

    discord = FakeDiscord()

    code = announce(tmp_path, discord, post=unreachable)

    assert code == 1
    assert discord.output()
    assert "sentinel-webhook-token" not in discord.output()
    assert "123456" not in discord.output()
