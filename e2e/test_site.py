"""AC25: the browser tests can point at a running site instead of Django's own."""

import pytest

from e2e.site import access_headers, remote_site

STAGING = "https://cucumber-staging.example.com"


def test_no_site_url_means_the_local_live_server() -> None:
    assert remote_site({}) is None
    assert remote_site({"E2E_SITE_URL": "  "}) is None


def test_site_url_is_used_without_a_trailing_slash() -> None:
    assert remote_site({"E2E_SITE_URL": f"{STAGING}/"}) == STAGING


def test_site_url_must_be_https() -> None:
    with pytest.raises(ValueError, match="https://"):
        remote_site({"E2E_SITE_URL": "http://cucumber-staging.example.com"})


def test_no_access_token_means_no_extra_headers() -> None:
    assert access_headers({}) == {}


def test_access_token_becomes_cloudflare_headers() -> None:
    environ = {
        "E2E_ACCESS_CLIENT_ID": "id.access",
        "E2E_ACCESS_CLIENT_SECRET": "s3cret",
    }

    assert access_headers(environ) == {
        "CF-Access-Client-Id": "id.access",
        "CF-Access-Client-Secret": "s3cret",
    }


@pytest.mark.parametrize("name", ["E2E_ACCESS_CLIENT_ID", "E2E_ACCESS_CLIENT_SECRET"])
def test_half_an_access_token_is_refused(name: str) -> None:
    with pytest.raises(ValueError, match="both"):
        access_headers({name: "value"})
