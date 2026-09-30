import os
from types import SimpleNamespace

import pytest

from pkgcore.fetch import errors, fetchable, mirror, uri_list
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


class Observer:
    def __init__(self):
        self.errors = []

    def error(self, msg, *args):
        self.errors.append(msg % args if args else msg)

    def flush(self):
        pass


class TestFetchBase:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.distdir = str(tmp_path)
        domain = SimpleNamespace(
            distdir=self.distdir,
            settings={"FETCHCOMMAND": "wget ${URI} -O ${DISTDIR}/${FILE}"},
            get_settings_envvar=lambda name, default: default,
        )
        self.fetch = format.fetch_base(domain, pkg=None, fetchables=())
        self.calls = []
        self.observer = Observer()

    def target(self, filename="foo.tar.gz"):
        uris = uri_list(filename)
        uris.add_mirror(mirror(["https://mirror.example.org"], "gentoo"))
        uris.add_uri("https://upstream.example.org/foo.tar.gz")
        return fetchable(filename, uri=uris, chksums={})

    def fake_fetcher(self, *outcomes):
        """Each call pops an outcome: an exception to raise, or True to succeed"""
        outcomes = list(outcomes)

        def fetcher(target):
            self.calls.append(target)
            path = os.path.join(self.distdir, target.filename)
            with open(path, "w") as f:
                f.write("content")
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return path

        self.fetch.fetcher = fetcher

    def test_checksum_failure_refetches_from_upstream(self):
        target = self.target()
        self.fake_fetcher(
            errors.ChksumFailure("foo.tar.gz", chksum="size", expected=1, value=2), True
        )
        assert self.fetch.fetch_one(target, self.observer)
        failed = os.path.join(self.distdir, "foo.tar.gz._failed_chksum_")
        assert os.path.exists(failed)
        # the retry skips the mirrors
        assert list(self.calls[1].uri) == ["https://upstream.example.org/foo.tar.gz"]
        assert any("refetching from upstream" in x for x in self.observer.errors)

    def test_second_checksum_failure_is_raised(self):
        failure = errors.ChksumFailure("foo.tar.gz", chksum="size", expected=1, value=2)
        self.fake_fetcher(failure, failure)
        with pytest.raises(errors.ChksumFailure):
            self.fetch.fetch_one(self.target(), self.observer)

    def test_fetch_failure_is_reported(self):
        self.fake_fetcher(errors.FetchFailed("foo.tar.gz", "nope"))
        target = self.target()
        self.fetch.fetchables = [target]
        verified, failures = self.fetch.fetch_all(self.observer)
        assert failures == [target]
        assert verified == {}

    def test_same_filename_is_fetched_once(self):
        self.fake_fetcher(True)
        first, second = self.target(), self.target()
        self.fetch.fetchables = [first, second]
        verified, failures = self.fetch.fetch_all(self.observer)
        assert failures == []
        assert len(self.calls) == 1
        assert list(verified.values()) == [first]
