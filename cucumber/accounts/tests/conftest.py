"""Accounts for the U0.5 tests: the Owner (Admin), Gene and Pim (Techs).

Each can log in with `PASSWORD`. Django's real password hasher takes a
noticeable moment by design; these tests use a fast one, except where a test
is about the hasher itself.
"""

from collections.abc import Iterator

import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings

from cucumber.accounts.tests.helpers import PASSWORD, signed_in
from cucumber.core.tests.stock import make_staff

FAST_HASHER = "django.contrib.auth.hashers.MD5PasswordHasher"


@pytest.fixture(autouse=True)
def fast_passwords() -> Iterator[None]:
    with override_settings(PASSWORD_HASHERS=[FAST_HASHER]):
        yield


@pytest.fixture
def owner(db: None) -> User:
    """Jade, the Owner, the only Admin."""
    return make_staff("jade", "admin", PASSWORD)


@pytest.fixture
def gene(db: None) -> User:
    return make_staff("gene", "tech", PASSWORD)


@pytest.fixture
def pim(db: None) -> User:
    return make_staff("pim", "tech", PASSWORD)


@pytest.fixture
def owner_client(owner: User) -> Client:
    return signed_in(owner)


@pytest.fixture
def gene_client(gene: User) -> Client:
    return signed_in(gene)
