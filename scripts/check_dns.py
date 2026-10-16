"""Check that every record in a GoDaddy DNS export answers the same now (AC15).

Before the nameserver switch, ask one of Cloudflare's assigned nameservers;
after it, leave `--server` out to ask the public internet as well
(docs/roadmap/units/u0.4b-design.md §4–§5):

    uv run --no-dev python -m scripts.check_dns ~/Documents/southeastcanopy.com.txt \\
      --server <one of Cloudflare's nameservers>

Without `--server` dig asks this computer's usual resolver, which can still
answer from GoDaddy's cached records for a while; those match too. So after
the switch run it both ways, and read the "nameservers" line the plain run
prints: it should show Cloudflare's two names.

Prints one line per name and type, then "all records match" or "N problems".
Exits 0 when all match, 1 on any problem, 2 when it couldn't check at all.
SOA and the domain's own NS records are left out: they are meant to change.
"""

import argparse
import ipaddress
import re
import sys
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

from scripts.commands import Runner, run_command

CHECKED_TYPES = frozenset({"A", "AAAA", "CNAME", "MX", "TXT", "SRV", "CAA"})
# A proxied record answers with Cloudflare's addresses (A, AAAA) or not at all
# (a flattened CNAME), so these are the types where "proxied" is the likely cause.
PROXY_HINT_TYPES = frozenset({"A", "AAAA", "CNAME"})
PROXY_HINT = "is it set to DNS only?"
CLASSES = frozenset({"IN", "CH", "HS", "CS"})
TTL_PATTERN = re.compile(r"\d+([smhdw]\d*)*", re.IGNORECASE)
DIG_OPTIONS = ["+short", "+time=5", "+tries=2"]  # a dead server fails in seconds
SHORTEN_OVER = 60
SHORTEN_KEEP = 28  # characters kept at each end of a long value


class ZoneError(ValueError):
    """The zone file can't be read as records; the message names the line."""


@dataclass(frozen=True)
class Record:
    name: str  # lower case, no trailing dot
    type: str
    value: str  # written one way, so the file's and dig's can be compared


@dataclass(frozen=True)
class Zone:
    records: list[Record]  # the types this script checks
    unchecked: list[Record]  # every other type, listed so none is skipped silently
    apex: str | None  # the domain itself: the first origin


@dataclass(frozen=True)
class Result:
    name: str
    record_type: str
    status: str  # "ok", "missing" or "different"
    expected: frozenset[str]
    got: frozenset[str]
    hint: str


Token = tuple[str, bool]  # (text, was it in quotes)


# ---- reading zone text ----------------------------------------------------


def tokenize(line: str) -> list[Token]:
    """Split one line into fields; quotes keep spaces and `;`, `;` starts a comment."""
    tokens: list[Token] = []
    index = 0
    while index < len(line):
        char = line[index]
        if char.isspace():
            index += 1
        elif char == ";":
            break
        elif char in "()":
            tokens.append((char, False))
            index += 1
        elif char == '"':
            text, index = read_quoted(line, index + 1)
            tokens.append((text, True))
        else:
            end = index
            while (
                end < len(line) and not line[end].isspace() and line[end] not in '();"'
            ):
                end += 1
            tokens.append((line[index:end], False))
            index = end
    return tokens


def read_quoted(line: str, index: int) -> tuple[str, int]:
    """Text up to the closing quote, with `\\"`, `\\\\` and `\\DDD` decoded.

    `\\DDD` is one byte (dig writes non-ASCII text as UTF-8 bytes this way).
    Raises ValueError if the line ends before the closing quote.
    """
    parts = bytearray()
    while index < len(line) and line[index] != '"':
        if line[index] == "\\" and index + 1 < len(line):
            digits = line[index + 1 : index + 4]
            if len(digits) == 3 and digits.isdigit():
                parts.append(int(digits) % 256)
                index += 4
                continue
            parts += line[index + 1].encode()
            index += 2
            continue
        parts += line[index].encode()
        index += 1
    if index >= len(line):
        raise ValueError("a quote is never closed")
    return parts.decode("utf-8", errors="replace"), index + 1


def logical_lines(text: str) -> Iterator[tuple[int, bool, list[Token]]]:
    """(line number, starts indented, fields), joining lines inside ( )."""
    pending: list[Token] = []
    start, indented, depth = 0, False, 0
    for number, line in enumerate(text.splitlines(), start=1):
        try:
            tokens = tokenize(line)
        except ValueError as error:
            raise ZoneError(f"line {number}: {error}") from error
        if not pending:
            start, indented = number, line[:1].isspace()
        for token in tokens:
            if token == ("(", False):
                depth += 1
            elif token == (")", False):
                depth -= 1
            else:
                pending.append(token)
        if depth == 0 and pending:
            yield start, indented, pending
            pending = []
    if depth:
        raise ZoneError(f"line {start}: a '(' is never closed")


def qualify(name: str, origin: str) -> str:
    """A full name, lower case, without the trailing dot. `@` is the origin."""
    if name == "@":
        full = origin
    elif name.endswith(".") or not origin:
        full = name.rstrip(".")
    else:
        full = f"{name}.{origin}"
    return full.lower()


def normalize_value(record_type: str, fields: list[Token], origin: str) -> str:
    """The record's value written one way. Raises ValueError if it's malformed."""
    texts = [text for text, _ in fields]
    if record_type == "TXT":
        if not texts:
            raise ValueError("TXT needs a value")
        return "".join(texts)
    sizes = {"A": 1, "AAAA": 1, "CNAME": 1, "MX": 2, "SRV": 4, "CAA": 3}
    if len(texts) != sizes[record_type]:
        raise ValueError(
            f"{record_type} needs {sizes[record_type]} values, got {len(texts)}"
        )
    if record_type == "A":
        return str(ipaddress.IPv4Address(texts[0]))
    if record_type == "AAAA":
        return ipaddress.IPv6Address(texts[0]).compressed
    if record_type == "CNAME":
        return qualify(texts[0], origin)
    if record_type == "MX":
        return f"{int(texts[0])} {qualify(texts[1], origin)}"
    if record_type == "SRV":
        priority, weight, port = (int(text) for text in texts[:3])
        return f"{priority} {weight} {port} {qualify(texts[3], origin)}"
    flags, tag, value = texts  # CAA
    return f'{int(flags)} {tag.lower()} "{value}"'


def split_record(
    tokens: list[Token], indented: bool, previous_owner: str | None, origin: str
) -> tuple[str, str, list[Token]]:
    """(owner name, type, value fields). An indented line reuses the last owner."""
    if indented:
        if previous_owner is None:
            raise ValueError("the first record has no name")
        owner, fields = previous_owner, tokens
    else:
        owner, fields = qualify(tokens[0][0], origin), tokens[1:]
    while fields and (
        TTL_PATTERN.fullmatch(fields[0][0]) or fields[0][0].upper() in CLASSES
    ):
        fields = fields[1:]
    if not fields:
        raise ValueError("no record type")
    return owner, fields[0][0].upper(), fields[1:]


def parse_zone(text: str, origin: str | None = None) -> Zone:
    """Every record in a zone file, split into checked and not-checked types."""
    current = qualify(origin, "") if origin else None
    apex = current
    records: list[Record] = []
    unchecked: list[Record] = []
    previous_owner: str | None = None
    for number, indented, tokens in logical_lines(text):
        first = tokens[0][0]
        if first.upper() == "$ORIGIN" and len(tokens) == 2:
            current = qualify(tokens[1][0], "")
            apex = apex or current
            continue
        if first.upper() == "$TTL":
            continue
        if first.startswith("$"):
            raise ZoneError(f"line {number}: {first.upper()} is not supported")
        if current is None:
            raise ZoneError(
                f"line {number}: no $ORIGIN before the first record; pass --origin"
            )
        try:
            owner, record_type, fields = split_record(
                tokens, indented, previous_owner, current
            )
            previous_owner = owner
            if record_type == "SOA" or (record_type == "NS" and owner == apex):
                continue
            if record_type not in CHECKED_TYPES:
                value = " ".join(text for text, _ in fields)
                unchecked.append(Record(owner, record_type, value))
                continue
            value = normalize_value(record_type, fields, current)
        except ValueError as error:
            raise ZoneError(f"line {number}: {error}") from error
        records.append(Record(owner, record_type, value))
    return Zone(records, unchecked, apex)


# ---- asking dig and comparing ---------------------------------------------


def dig_command(name: str, record_type: str, server: str | None) -> list[str]:
    """`dig +short` for one name and type. Refuses values dig would read as options."""
    for value in (name, server or ""):
        if value.startswith(("-", "+", "@")):
            raise ValueError(f"{value!r} would be read by dig as an option")
    at_server = [f"@{server}"] if server else []
    return ["dig", *DIG_OPTIONS, *at_server, name, record_type]


def ask(run: Runner, name: str, record_type: str, server: str | None) -> list[str]:
    """The answer lines. dig's own `;;` status lines are not answers; if that is
    all it printed (it can exit 0 after a timeout), raise RuntimeError.
    """
    lines = [
        line.strip()
        for line in run(dig_command(name, record_type, server)).splitlines()
    ]
    answers = [line for line in lines if line and not line.startswith(";")]
    status = [line for line in lines if line.startswith(";")]
    if status and not answers:
        raise RuntimeError(f"dig {name} {record_type}: {status[0].lstrip('; ')}")
    return answers


def parse_answer(record_type: str, line: str) -> str:
    """One line of `dig +short`, written like the zone file's value."""
    try:
        return normalize_value(record_type, tokenize(line), origin="")
    except ValueError:
        return line.strip()  # not what was asked for (e.g. a CNAME on the way)


def compare(
    expected: Iterable[Record], run: Runner, server: str | None
) -> list[Result]:
    """Ask once per name and type; compare the answers with the file's as sets."""
    wanted: dict[tuple[str, str], set[str]] = {}
    for record in expected:
        wanted.setdefault((record.name, record.type), set()).add(record.value)
    results: list[Result] = []
    for (name, record_type), values in wanted.items():
        got = frozenset(
            parse_answer(record_type, line)
            for line in ask(run, name, record_type, server)
        )
        if got == values:
            status = "ok"
        else:
            status = "different" if got else "missing"
        hint = PROXY_HINT if status != "ok" and record_type in PROXY_HINT_TYPES else ""
        results.append(Result(name, record_type, status, frozenset(values), got, hint))
    return results


# ---- the report -------------------------------------------------------------


def shorten(value: str) -> str:
    """Long values (DKIM keys) as their start and end only."""
    if len(value) <= SHORTEN_OVER:
        return value
    return f"{value[:SHORTEN_KEEP]}…{value[-SHORTEN_KEEP:]}"


def listed(values: Iterable[str]) -> str:
    return ", ".join(sorted(shorten(value) for value in values))


def result_line(result: Result) -> str:
    line = f"{result.status:<11} {result.record_type:<5} {result.name}"
    if result.status == "missing":
        line += f": expected {listed(result.expected)}"
    elif result.status == "different":
        line += f": expected {listed(result.expected)}; got {listed(result.got)}"
    return f"{line} ({result.hint})" if result.hint else line


def format_report(results: Sequence[Result], unchecked: Sequence[Record]) -> list[str]:
    lines = [result_line(result) for result in results]
    lines += [
        f"{'not checked':<11} {record.type:<5} {record.name}: {shorten(record.value)}"
        for record in unchecked
    ]
    if unchecked:
        lines.append(
            f"{len(unchecked)} not checked: check by hand in Cloudflare's DNS page"
        )
    problems = sum(result.status != "ok" for result in results)
    if problems == 0 and unchecked:
        lines.append(f"all checked records match; {len(unchecked)} not checked")
    elif problems == 0:
        lines.append("all records match")
    else:
        lines.append(f"{problems} problem{'s' if problems > 1 else ''}")
    return lines


# ---- command line ---------------------------------------------------------


def main(argv: Sequence[str] | None = None, run: Runner = run_command) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "zone_file", type=Path, help="the zone file exported from GoDaddy"
    )
    parser.add_argument("--server", help="ask only this nameserver (before the switch)")
    parser.add_argument("--origin", help="the domain, if the file has no $ORIGIN line")
    args = parser.parse_args(argv)
    try:
        text = args.zone_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        print(f"check_dns: can't read {args.zone_file}: {error}", file=sys.stderr)
        return 2
    try:
        zone = parse_zone(text, args.origin)
    except ZoneError as error:
        print(f"check_dns: {args.zone_file}: {error}", file=sys.stderr)
        return 2
    if not zone.records:  # a wrong or empty file must never pass
        print(f"check_dns: {args.zone_file}: no records to check", file=sys.stderr)
        return 2
    try:
        results = compare(zone.records, run, args.server)
        lines = format_report(results, zone.unchecked)
        if not args.server and zone.apex:
            nameservers = ask(run, zone.apex, "NS", None)
            listed_ns = listed(qualify(ns, "") for ns in nameservers) or "no answer"
            lines.insert(-1, f"nameservers {zone.apex}: {listed_ns}")
    except (ValueError, RuntimeError, OSError) as error:  # dig failed or missing
        print(f"check_dns: couldn't ask DNS: {error}", file=sys.stderr)
        return 2
    print("\n".join(lines))
    return 0 if all(result.status == "ok" for result in results) else 1


if __name__ == "__main__":
    sys.exit(main())
