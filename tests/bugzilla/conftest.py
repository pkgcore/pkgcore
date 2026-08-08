"""Thin adapters over the shipped replay helpers.

The real machinery lives in :mod:`pkgcore.bugzilla.testing` so downstream
projects can use it; the ``bugzilla_cassette`` fixture comes from pkgcore's
pytest plugin. These fixtures only save the local tests a line or two.
"""

import pytest

from pkgcore.bugzilla.testing import API_KEY, Recording


@pytest.fixture
def cassette(bugzilla_cassette):
    """Queue recordings and hand back the cassette plus a transport"""

    def build(*recordings: Recording, api_key: str | None = API_KEY, **kwargs):
        bugzilla_cassette.api_key = api_key
        bugzilla_cassette.expect(*recordings)
        return bugzilla_cassette, bugzilla_cassette.transport(**kwargs)

    return build


@pytest.fixture
def client(bugzilla_cassette):
    """Queue recordings and hand back the cassette plus a client"""

    def build(*recordings: Recording, api_key: str | None = API_KEY, **kwargs):
        bugzilla_cassette.api_key = api_key
        bugzilla_cassette.expect(*recordings)
        return bugzilla_cassette, bugzilla_cassette.client(**kwargs)

    return build
