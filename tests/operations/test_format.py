from types import SimpleNamespace

import pytest

from pkgcore.fetch import fetchable
from pkgcore.operations import OperationError, format


class FailingFetcher:
    def __init__(self, domain, pkg, fetchables, distdir):
        self.fetchables = fetchables

    def fetch_all(self, observer):
        return {}, list(self.fetchables)


def test_fetch_failure_without_observer():
    pkg = SimpleNamespace(
        fetchables=[fetchable("foo.tar.gz", uri=["https://example.org/foo"])],
        restrict=(),
        unversioned_atom="cat/pkg",
        repo=SimpleNamespace(repo_id="gentoo"),
    )
    ops = format.operations(domain=None, pkg=pkg)
    ops._fetch_kls = FailingFetcher
    with pytest.raises(OperationError) as excinfo:
        ops.fetch()
    assert isinstance(excinfo.value.__cause__, format.FetchError)
