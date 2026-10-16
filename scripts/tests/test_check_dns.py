"""AC15: every DNS record in the GoDaddy export answers the same at Cloudflare."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from scripts.check_dns import (
    Record,
    ZoneError,
    compare,
    dig_command,
    format_report,
    main,
    parse_zone,
    shorten,
)

ORIGIN = "southeastcanopy.com"

# Shaped like a GoDaddy export: SOA over several lines, comments, `@`,
# relative names, a blank owner, TTL and class in either order.
GODADDY_EXPORT = """\
; Domain: southeastcanopy.com
; Exported (y-m-d hh:mm:ss): 2026-10-16 10:00:00
$ORIGIN southeastcanopy.com.
$TTL 3600

; SOA Record
@\t3600\t IN \tSOA\tns51.domaincontrol.com.\tdns.jomax.net. (
\t\t\t\t\t2026101600
\t\t\t\t\t28800
\t\t\t\t\t7200
\t\t\t\t\t604800
\t\t\t\t\t3600
\t\t\t\t\t)

; A Record
@\t600\t IN \tA\t76.223.105.230
@\t600\t IN \tA\t13.248.243.5

; CNAME Record
www\t3600\t IN \tCNAME\t@
autodiscover\t3600\t IN \tCNAME\tautodiscover.outlook.com.
selector1._domainkey\t3600\t IN \tCNAME\ts1-sec._domainkey.sec.onmicrosoft.com.

; MX Record
@\t3600\t IN \tMX\t0\tsoutheastcanopy-com.mail.protection.outlook.com.

; TXT Record
@\t3600\t IN \tTXT\t"v=spf1 include:spf.protection.outlook.com -all"
\t\tIN 3600 TXT\t"MS=ms12345678"

; SRV Record
_sip._tls\t3600\t IN \tSRV\t100\t1\t443\tsipdir.online.lync.com.

; NS Record
@\t3600\t IN \tNS\tns51.domaincontrol.com.
@\t3600\t IN \tNS\tns52.domaincontrol.com.
"""


def records_of(text: str) -> set[Record]:
    return set(parse_zone(text).records)


# ---- reading the zone file ------------------------------------------------


def test_reads_every_checked_record_from_a_godaddy_export() -> None:
    zone = parse_zone(GODADDY_EXPORT)

    assert set(zone.records) == {
        Record(ORIGIN, "A", "76.223.105.230"),
        Record(ORIGIN, "A", "13.248.243.5"),
        Record(f"www.{ORIGIN}", "CNAME", ORIGIN),
        Record(f"autodiscover.{ORIGIN}", "CNAME", "autodiscover.outlook.com"),
        Record(
            f"selector1._domainkey.{ORIGIN}",
            "CNAME",
            "s1-sec._domainkey.sec.onmicrosoft.com",
        ),
        Record(ORIGIN, "MX", "0 southeastcanopy-com.mail.protection.outlook.com"),
        Record(ORIGIN, "TXT", "v=spf1 include:spf.protection.outlook.com -all"),
        Record(ORIGIN, "TXT", "MS=ms12345678"),
        Record(f"_sip._tls.{ORIGIN}", "SRV", "100 1 443 sipdir.online.lync.com"),
    }


def test_soa_and_the_domains_own_ns_records_are_left_out() -> None:
    # They are meant to change when the nameservers move.
    zone = parse_zone(GODADDY_EXPORT)

    assert all(record.type not in {"SOA", "NS"} for record in zone.records)
    assert zone.unchecked == []


def test_origin_can_be_given_when_the_file_has_none() -> None:
    zone = parse_zone("www 3600 IN A 192.0.2.1\n", origin="Example.COM.")

    assert zone.records == [Record("www.example.com", "A", "192.0.2.1")]


def test_a_file_with_no_origin_is_refused() -> None:
    with pytest.raises(ZoneError, match=r"\$ORIGIN"):
        parse_zone("www 3600 IN A 192.0.2.1\n")


def test_origin_can_change_part_way_through() -> None:
    text = (
        "$ORIGIN example.com.\nwww A 192.0.2.1\n"
        "$ORIGIN sub.example.com.\napi A 192.0.2.2\n"
    )

    assert records_of(text) == {
        Record("www.example.com", "A", "192.0.2.1"),
        Record("api.sub.example.com", "A", "192.0.2.2"),
    }


def test_names_are_compared_without_case_or_trailing_dot() -> None:
    text = "$ORIGIN example.com.\nWWW.Example.com. 600 IN CNAME Target.Example.NET.\n"

    assert records_of(text) == {
        Record("www.example.com", "CNAME", "target.example.net")
    }


def test_relative_targets_get_the_origin() -> None:
    text = (
        "$ORIGIN example.com.\n@ MX 10 mail\nshop CNAME www\n_x._tcp SRV 0 5 443 host\n"
    )

    assert records_of(text) == {
        Record("example.com", "MX", "10 mail.example.com"),
        Record("shop.example.com", "CNAME", "www.example.com"),
        Record("_x._tcp.example.com", "SRV", "0 5 443 host.example.com"),
    }


def test_txt_in_several_parts_is_joined() -> None:
    text = '$ORIGIN example.com.\n@ TXT "v=DKIM1; k=rsa; " "p=MIIBIjAN"\n'

    assert records_of(text) == {
        Record("example.com", "TXT", "v=DKIM1; k=rsa; p=MIIBIjAN")
    }


def test_semicolons_inside_quotes_are_not_comments() -> None:
    text = '$ORIGIN example.com.\n@ TXT "a;b" ; the comment\n'

    assert records_of(text) == {Record("example.com", "TXT", "a;b")}


def test_escaped_quotes_inside_txt_are_kept() -> None:
    text = '$ORIGIN example.com.\n@ TXT "say \\"hi\\""\n'

    assert records_of(text) == {Record("example.com", "TXT", 'say "hi"')}


def test_characters_written_as_three_digits_are_decoded() -> None:
    # dig prints some characters as \DDD; the zone file may too.
    text = '$ORIGIN example.com.\n@ TXT "a\\059b"\n'

    assert records_of(text) == {Record("example.com", "TXT", "a;b")}


@pytest.mark.parametrize(
    ("line", "problem"),
    [
        ("@ 3600 IN TXT", "TXT needs a value"),
        ("@ 3600 IN", "no record type"),
        ("   3600 IN A 192.0.2.1", "no name"),
    ],
)
def test_incomplete_records_name_their_line(line: str, problem: str) -> None:
    with pytest.raises(ZoneError, match=f"line 2: .*{problem}"):
        parse_zone(f"$ORIGIN example.com.\n{line}\n")


def test_ipv6_addresses_are_written_one_way() -> None:
    text = "$ORIGIN example.com.\n@ AAAA 2001:0DB8:0000:0000:0000:0000:0000:0001\n"

    assert records_of(text) == {Record("example.com", "AAAA", "2001:db8::1")}


def test_caa_records_are_read() -> None:
    text = '$ORIGIN example.com.\n@ 3600 IN CAA 0 ISSUE "letsencrypt.org"\n'

    assert records_of(text) == {
        Record("example.com", "CAA", '0 issue "letsencrypt.org"')
    }


def test_other_types_are_listed_as_not_checked_never_dropped() -> None:
    text = (
        "$ORIGIN example.com.\n"
        "@ 300 IN HTTPS 1 . alpn=h2\n"
        "sub 3600 IN NS ns1.other.net.\n"  # a delegation is not the domain's own NS
    )
    zone = parse_zone(text)

    assert zone.records == []
    assert [(r.name, r.type) for r in zone.unchecked] == [
        ("example.com", "HTTPS"),
        ("sub.example.com", "NS"),
    ]


def test_a_bad_address_names_its_line() -> None:
    with pytest.raises(ZoneError, match="line 2"):
        parse_zone("$ORIGIN example.com.\n@ A 300.1.1.1\n")


def test_a_record_with_too_few_fields_names_its_line() -> None:
    with pytest.raises(ZoneError, match="line 2"):
        parse_zone("$ORIGIN example.com.\n@ MX 10\n")


def test_include_is_refused() -> None:
    with pytest.raises(ZoneError, match=r"\$INCLUDE"):
        parse_zone("$ORIGIN example.com.\n$INCLUDE other.zone\n")


def test_an_unclosed_quote_is_refused() -> None:
    # A cut-off DKIM key must not become the value everything is compared with.
    with pytest.raises(ZoneError, match="line 2: .*quote"):
        parse_zone('$ORIGIN example.com.\n@ TXT "v=DKIM1; p=MIIB\n')


def test_three_digit_escapes_are_read_as_utf8_bytes() -> None:
    text = '$ORIGIN example.com.\n@ TXT "caf\\195\\169"\n'

    assert records_of(text) == {Record("example.com", "TXT", "café")}


@pytest.mark.parametrize("ttl", ["600", "1h", "1w2d", "30M"])
def test_ttls_in_any_form_are_skipped(ttl: str) -> None:
    text = f"$ORIGIN example.com.\n@ {ttl} IN A 192.0.2.1\n"

    assert records_of(text) == {Record("example.com", "A", "192.0.2.1")}


def test_an_indented_line_keeps_the_owner_across_an_origin_change() -> None:
    text = (
        "$ORIGIN example.com.\nwww A 192.0.2.1\n"
        "$ORIGIN sub.example.com.\n  A 192.0.2.2\n"
    )

    assert records_of(text) == {
        Record("www.example.com", "A", "192.0.2.1"),
        Record("www.example.com", "A", "192.0.2.2"),
    }


def test_an_unclosed_bracket_is_refused() -> None:
    with pytest.raises(ZoneError, match=r"\("):
        parse_zone("$ORIGIN example.com.\n@ SOA a. b. ( 1 2 3\n")


# ---- asking dig and comparing ---------------------------------------------


class FakeDig:
    """Answers `dig +short` from a dict of (name, type) -> printed lines."""

    def __init__(self, answers: dict[tuple[str, str], str]) -> None:
        self.answers = answers
        self.commands: list[list[str]] = []

    def __call__(self, command: Sequence[str]) -> str:
        self.commands.append(list(command))
        name, record_type = command[-2], command[-1]
        return self.answers.get((name, record_type), "")


EXPECTED = [
    Record("example.com", "A", "192.0.2.1"),
    Record("example.com", "A", "192.0.2.2"),
    Record("example.com", "MX", "10 mail.example.com"),
    Record("example.com", "TXT", "v=spf1 -all"),
]


def all_answers() -> dict[tuple[str, str], str]:
    return {
        ("example.com", "A"): "192.0.2.2\n192.0.2.1\n",  # order doesn't matter
        ("example.com", "MX"): "10 MAIL.example.com.\n",
        ("example.com", "TXT"): '"v=spf1 " "-all"\n',
    }


def test_dig_command_asks_one_server_when_given() -> None:
    # A dead server fails in seconds, not dig's default of 15+.
    assert dig_command("example.com", "MX", "ns1.cf.com") == [
        "dig", "+short", "+time=5", "+tries=2", "@ns1.cf.com", "example.com", "MX",
    ]  # fmt: skip
    assert dig_command("example.com", "MX", None) == [
        "dig", "+short", "+time=5", "+tries=2", "example.com", "MX",
    ]  # fmt: skip


@pytest.mark.parametrize("server", ["-f/etc/passwd", "+tcp"])
def test_dig_command_refuses_values_dig_would_read_as_options(server: str) -> None:
    with pytest.raises(ValueError, match="option"):
        dig_command("example.com", "MX", server)


def test_dig_status_lines_are_not_answers() -> None:
    answers = all_answers()
    answers[("example.com", "MX")] = (
        ";; Truncated, retrying in TCP mode.\n10 mail.example.com.\n"
    )

    (mx,) = [
        r for r in compare(EXPECTED, FakeDig(answers), None) if r.record_type == "MX"
    ]

    assert mx.status == "ok"


def test_a_dig_error_printed_as_an_answer_stops_the_check() -> None:
    # dig can exit 0 and print only an error line, e.g. after a timeout.
    answers = all_answers()
    answers[("example.com", "MX")] = (
        ";; communications error to 1.1.1.1#53: timed out\n"
    )

    with pytest.raises(RuntimeError, match="timed out"):
        compare(EXPECTED, FakeDig(answers), None)


def test_a_long_txt_split_by_dig_into_chunks_matches() -> None:
    key = "v=DKIM1; k=rsa; p=" + "A" * 400
    expected = [Record("example.com", "TXT", key)]
    chunked = f'"{key[:255]}" "{key[255:]}"\n'

    (result,) = compare(expected, FakeDig({("example.com", "TXT"): chunked}), None)

    assert result.status == "ok"


def test_a_cname_on_the_way_to_an_address_is_different() -> None:
    expected = [Record("example.com", "A", "192.0.2.1")]
    chain = "target.example.net.\n192.0.2.1\n"

    (result,) = compare(expected, FakeDig({("example.com", "A"): chain}), None)

    assert result.status == "different"


def test_matching_answers_are_ok() -> None:
    results = compare(EXPECTED, FakeDig(all_answers()), server="ns1.cf.com")

    assert [(r.record_type, r.status) for r in results] == [
        ("A", "ok"),
        ("MX", "ok"),
        ("TXT", "ok"),
    ]


def test_each_name_and_type_is_asked_once() -> None:
    dig = FakeDig(all_answers())

    compare(EXPECTED, dig, server="ns1.cf.com")

    assert len(dig.commands) == 3
    assert all("@ns1.cf.com" in command for command in dig.commands)


def test_no_answer_is_missing() -> None:
    answers = all_answers()
    del answers[("example.com", "TXT")]

    (txt,) = [
        r for r in compare(EXPECTED, FakeDig(answers), None) if r.record_type == "TXT"
    ]

    assert txt.status == "missing"


def test_one_value_short_is_different() -> None:
    answers = all_answers()
    answers[("example.com", "A")] = "192.0.2.1\n"

    (a,) = [
        r for r in compare(EXPECTED, FakeDig(answers), None) if r.record_type == "A"
    ]

    assert a.status == "different"
    assert a.got == frozenset({"192.0.2.1"})


def test_a_proxied_address_gets_the_dns_only_hint() -> None:
    answers = all_answers()
    answers[("example.com", "A")] = "104.21.5.5\n172.67.1.1\n"  # Cloudflare's

    (a,) = [
        r for r in compare(EXPECTED, FakeDig(answers), None) if r.record_type == "A"
    ]

    assert a.status == "different"
    assert a.hint == "is it set to DNS only?"


def test_a_proxied_cname_answers_nothing_and_gets_the_hint() -> None:
    # Cloudflare flattens a proxied CNAME, so a CNAME question gets no answer.
    expected = [Record("www.example.com", "CNAME", "example.com")]

    (result,) = compare(expected, FakeDig({}), None)

    assert result.status == "missing"
    assert result.hint == "is it set to DNS only?"


def test_mail_records_get_no_proxy_hint() -> None:
    answers = all_answers()
    answers[("example.com", "MX")] = "20 other.example.com.\n"

    (mx,) = [
        r for r in compare(EXPECTED, FakeDig(answers), None) if r.record_type == "MX"
    ]

    assert mx.hint == ""


def test_an_answer_dig_prints_oddly_is_compared_as_text() -> None:
    expected = [Record("example.com", "A", "192.0.2.1")]

    (result,) = compare(expected, FakeDig({("example.com", "A"): "not-an-ip\n"}), None)

    assert result.status == "different"
    assert result.got == frozenset({"not-an-ip"})


# ---- the report -------------------------------------------------------------


def test_long_txt_values_show_only_start_and_end() -> None:
    key = "v=DKIM1; k=rsa; p=" + "A" * 300 + "QAB"

    short = shorten(key)

    assert len(short) <= 60
    assert short.startswith("v=DKIM1; k=rsa;")
    assert short.endswith("QAB")
    assert shorten("v=spf1 -all") == "v=spf1 -all"


def test_report_says_all_records_match_when_they_do() -> None:
    results = compare(EXPECTED, FakeDig(all_answers()), None)

    lines = format_report(results, unchecked=[])

    assert lines[-1] == "all records match"
    assert all(line.startswith("ok") for line in lines[:-1])


def test_report_counts_problems_and_shows_expected_and_got() -> None:
    answers = all_answers()
    answers[("example.com", "A")] = "104.21.5.5\n"
    del answers[("example.com", "TXT")]

    lines = format_report(compare(EXPECTED, FakeDig(answers), None), unchecked=[])

    different = next(line for line in lines if line.startswith("different"))
    assert "expected 192.0.2.1, 192.0.2.2" in different
    assert "got 104.21.5.5" in different
    assert "is it set to DNS only?" in different
    assert any(line.startswith("missing") for line in lines)
    assert lines[-1] == "2 problems"


def test_report_lists_unchecked_records_for_a_check_by_hand() -> None:
    unchecked = [Record("example.com", "HTTPS", "1 . alpn=h2")]

    lines = format_report([], unchecked=unchecked)

    assert any(line.startswith("not checked") and "HTTPS" in line for line in lines)
    assert "check by hand" in lines[-2]


def test_report_never_says_all_records_match_while_some_were_not_checked() -> None:
    results = compare(EXPECTED, FakeDig(all_answers()), None)
    unchecked = [Record("example.com", "HTTPS", "1 . alpn=h2")]

    lines = format_report(results, unchecked=unchecked)

    assert lines[-1] == "all checked records match; 1 not checked"


# ---- main -----------------------------------------------------------------


def write_zone(tmp_path: Path) -> Path:
    path = tmp_path / "example.com.txt"
    path.write_text(
        "$ORIGIN example.com.\n@ A 192.0.2.1\n@ A 192.0.2.2\n"
        '@ MX 10 mail\n@ TXT "v=spf1 -all"\n'
    )
    return path


def test_main_exits_0_when_all_records_match(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [str(write_zone(tmp_path)), "--server", "ns1.cf.com"],
        run=FakeDig(all_answers()),
    )

    assert code == 0
    assert capsys.readouterr().out.rstrip().endswith("all records match")


def test_main_exits_1_on_any_problem(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main([str(write_zone(tmp_path))], run=FakeDig({}))

    assert code == 1
    assert capsys.readouterr().out.rstrip().endswith("3 problems")


def test_main_exits_2_when_the_file_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main([str(tmp_path / "nope.txt")], run=FakeDig({}))

    assert code == 2
    assert "nope.txt" in capsys.readouterr().err


def test_main_exits_2_on_a_bad_zone_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "bad.txt"
    path.write_text("@ A 192.0.2.1\n")  # no $ORIGIN

    code = main([str(path)], run=FakeDig({}))

    assert code == 2
    assert "$ORIGIN" in capsys.readouterr().err


def test_main_exits_2_when_dig_fails(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken_dig(command: Sequence[str]) -> str:
        raise RuntimeError("`dig` failed: connection timed out")

    code = main([str(write_zone(tmp_path))], run=broken_dig)

    assert code == 2
    assert "timed out" in capsys.readouterr().err


@pytest.mark.parametrize(
    "text",
    [
        "",
        "; only a comment\n",
        "$ORIGIN example.com.\n@ SOA a. b. 1 2 3 4 5\n@ NS ns1.example.net.\n",
        "$ORIGIN example.com.\n@ HTTPS 1 . alpn=h2\n",
    ],
)
def test_main_refuses_a_file_with_nothing_to_check(
    text: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # An empty or wrong file must never end in "all records match".
    path = tmp_path / "zone.txt"
    path.write_text(text)

    code = main([str(path), "--origin", "example.com"], run=FakeDig({}))

    assert code == 2
    assert "no records to check" in capsys.readouterr().err


def test_main_exits_2_when_dig_prints_only_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dig = FakeDig({("example.com", "A"): ";; connection timed out; no servers\n"})

    code = main([str(write_zone(tmp_path))], run=dig)

    assert code == 2
    assert "timed out" in capsys.readouterr().err


def test_main_exits_2_on_a_server_that_looks_like_an_option(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main([str(write_zone(tmp_path)), "--server=-f/etc/passwd"], run=FakeDig({}))

    assert code == 2
    assert "option" in capsys.readouterr().err


def test_main_uses_origin_for_a_file_without_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "zone.txt"
    path.write_text("@ A 192.0.2.1\n@ A 192.0.2.2\n")

    code = main(
        [str(path), "--origin", "example.com", "--server", "ns1.cf.com"],
        run=FakeDig(all_answers()),
    )

    assert code == 0


def test_without_a_server_it_shows_which_nameservers_answer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The public run can be answered from GoDaddy's cached records, which
    # match too; seeing the nameservers shows whether the switch has spread.
    answers = all_answers()
    answers[("example.com", "NS")] = "ada.ns.cloudflare.com.\nbob.ns.cloudflare.com.\n"

    main([str(write_zone(tmp_path))], run=FakeDig(answers))

    out = capsys.readouterr().out
    assert (
        "nameservers example.com: ada.ns.cloudflare.com, bob.ns.cloudflare.com" in out
    )


def test_with_a_server_it_does_not_ask_for_nameservers(tmp_path: Path) -> None:
    dig = FakeDig(all_answers())

    main([str(write_zone(tmp_path)), "--server", "ns1.cf.com"], run=dig)

    assert all(command[-1] != "NS" for command in dig.commands)
