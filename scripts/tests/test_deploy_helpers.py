"""AC10, AC11: the deploy command's small rules, each on its own."""

import json
from datetime import UTC, datetime

import pytest

from scripts.deploy import (
    IMAGES_KEPT,
    Pending,
    backup_name,
    check_version,
    format_duration,
    images_to_remove,
    is_version_tag,
    parse_pending,
    source_build,
)
from scripts.next_version import VERSION_PATTERN
from scripts.server import ServerError

GOOD_TAGS = ["2026.10.1", "2026.01.1", "2026.12.15", "2027.03.2"]
BAD_TAGS = [
    "2026.13.1",
    "2026.00.1",
    "2026.1.1",
    "v2026.10.1",
    "2026.10.1-rc1",
    "2026.10",
    "main",
    "feature/split-batch",
    "",
]


@pytest.mark.parametrize("tag", GOOD_TAGS)
def test_release_tags_are_recognised(tag: str) -> None:
    assert is_version_tag(tag)


@pytest.mark.parametrize("name", BAD_TAGS)
def test_anything_else_is_not_a_release_tag(name: str) -> None:
    assert not is_version_tag(name)


@pytest.mark.parametrize("name", GOOD_TAGS + BAD_TAGS)
def test_deploy_and_next_version_share_one_pattern(name: str) -> None:
    """Design M6: the version the Draft release makes is the one deploy accepts."""
    assert is_version_tag(name) == (VERSION_PATTERN.fullmatch(name) is not None)


@pytest.mark.parametrize("version", ["main", "feature/split-batch", "2026.13.1"])
def test_production_takes_release_tags_only(version: str) -> None:
    with pytest.raises(ServerError, match="tag"):
        check_version("production", version, from_source=False)


def test_production_never_builds_from_a_local_checkout() -> None:
    with pytest.raises(ServerError, match="--source"):
        check_version("production", "2026.10.1", from_source=True)


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_a_release_tag_is_accepted_everywhere(environment: str) -> None:
    check_version(environment, "2026.10.1", from_source=False)


def test_staging_may_also_run_main() -> None:
    check_version("staging", "main", from_source=False)


def test_staging_may_build_main_from_a_local_checkout() -> None:
    check_version("staging", "main", from_source=True)


def test_a_local_checkout_never_takes_a_release_tags_name() -> None:
    """G5 finding 1: it would take over that version's image."""
    with pytest.raises(ServerError, match="--source"):
        check_version("staging", "2026.10.1", from_source=True)


def test_each_local_checkout_build_is_named_for_its_time() -> None:
    started = datetime(2026, 10, 16, 4, 55, 52, tzinfo=UTC)

    assert source_build(started) == "source-2026-10-16-115552"


def test_a_local_checkout_build_name_needs_a_time_zone() -> None:
    with pytest.raises(ValueError, match="time zone"):
        source_build(datetime(2026, 10, 16, 4, 55, 52))  # noqa: DTZ001


@pytest.mark.parametrize("version", ["feature/split-batch", "develop", "2026.13.1"])
def test_staging_refuses_other_branches_and_bad_tags(version: str) -> None:
    with pytest.raises(ServerError):
        check_version("staging", version, from_source=False)


def test_pending_lists_both_kinds_of_difference() -> None:
    output = json.dumps({"pending": ["core.0005_a", "core.0006_b"], "unknown": []})

    assert parse_pending(output) == Pending(("core.0005_a", "core.0006_b"), ())


def test_pending_ignores_lines_printed_before_the_json() -> None:
    output = "Some warning from Django\n" + json.dumps(
        {"pending": [], "unknown": ["core.0099_future"]}
    )

    assert parse_pending(output) == Pending((), ("core.0099_future",))


@pytest.mark.parametrize("output", ["", "not json", '{"pending": 2}'])
def test_unreadable_pending_output_stops_the_deploy(output: str) -> None:
    with pytest.raises(ServerError, match="pending_migrations"):
        parse_pending(output)


def test_backup_name_uses_bangkok_time_and_the_version() -> None:
    now = datetime(2026, 10, 13, 7, 5, tzinfo=UTC)

    assert backup_name(now, "2026.10.1") == "2026-10-13-1405-before-2026.10.1.dump"


def test_backup_name_needs_a_time_zone() -> None:
    with pytest.raises(ValueError, match="time zone"):
        backup_name(datetime(2026, 10, 13, 14, 5), "2026.10.1")  # noqa: DTZ001


@pytest.mark.parametrize(
    ("seconds", "shown"),
    [(161, "2 min 41 s"), (45, "45 s"), (60, "1 min 0 s"), (0.4, "0 s")],
)
def test_duration_is_shown_in_minutes_and_seconds(seconds: float, shown: str) -> None:
    assert format_duration(seconds) == shown


def test_images_beyond_the_newest_three_are_removed() -> None:
    tags = ["2026.10.4", "2026.10.3", "2026.10.2", "2026.10.1", "2026.09.3"]

    assert IMAGES_KEPT == 3
    assert images_to_remove(tags) == ["2026.10.1", "2026.09.3"]


def test_the_version_to_roll_back_to_is_never_removed() -> None:
    tags = ["2026.10.4", "2026.10.3", "2026.10.2", "2026.10.1", "2026.09.3"]

    assert images_to_remove(tags, keep_also=["2026.09.3"]) == ["2026.10.1"]


def test_nothing_is_removed_while_there_are_three_or_fewer() -> None:
    assert images_to_remove(["2026.10.2", "2026.10.1"]) == []
