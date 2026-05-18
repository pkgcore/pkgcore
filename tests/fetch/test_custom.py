import os
from unittest import mock

import pytest

from pkgcore.fetch import custom, errors, fetchable


@pytest.fixture
def distdir(tmp_path):
    return str(tmp_path)


def make_fetcher(distdir: str, attempts=2):
    return custom.fetcher(
        distdir=distdir,
        command="false ${URI} -o ${FILE}",
        userpriv=False,
        attempts=attempts,
    )


def partial_content(path: str):
    with open(path, "wb") as f:
        f.write(b"partial download content")


class TestFetch:
    """Tests for fetch() when the fetchable has no checksums (new manifest generation)."""

    def test_failed_fetch_deletes_partial_file(self, distdir: str):
        """Non-zero fetcher exit with no checksums must clean up the partial file."""
        target = fetchable(
            "testfile.tar.gz",
            uri=["http://example.com/testfile.tar.gz"],
            chksums={},
        )
        fetcher = make_fetcher(distdir)
        partial_path = os.path.join(distdir, "testfile.tar.gz")

        def fake_spawn(cmd, **kwargs):
            partial_content(partial_path)
            return 92  # HTTP/2 stream error

        with mock.patch("pkgcore.fetch.custom.spawn_bash", side_effect=fake_spawn):
            with pytest.raises(errors.FetchFailed):
                fetcher.fetch(target)

        assert not os.path.exists(partial_path)

    def test_successful_fetch_keeps_file(self, distdir: str):
        """Zero exit with no checksums (file exists after download) must return the path."""
        target = fetchable(
            "testfile.tar.gz",
            uri=["http://example.com/testfile.tar.gz"],
            chksums={},
        )
        fetcher = make_fetcher(distdir)
        expected_path = os.path.join(distdir, "testfile.tar.gz")

        def fake_spawn(cmd, **kwargs):
            partial_content(expected_path)
            return 0

        with mock.patch("pkgcore.fetch.custom.spawn_bash", side_effect=fake_spawn):
            result = fetcher.fetch(target)

        assert result == expected_path
        assert os.path.exists(expected_path)

    def test_failed_fetch_no_partial_file_left(self, distdir: str):
        """Non-zero exit when no file was written should not raise OSError."""
        target = fetchable(
            "testfile.tar.gz",
            uri=["http://example.com/testfile.tar.gz"],
            chksums={},
        )
        fetcher = make_fetcher(distdir)

        with mock.patch("pkgcore.fetch.custom.spawn_bash", return_value=92):
            with pytest.raises(errors.FetchFailed):
                fetcher.fetch(target)

    def test_failed_fetch_keeps_partial_for_resume(self, distdir: str):
        """With checksums, a partial file is kept so the resume command can continue it."""
        from snakeoil import data_source
        from snakeoil.chksum import get_handlers

        full_data = b"complete file content for checksum"
        handlers = get_handlers()
        chksums = {
            chf: handlers[chf](data_source.data_source(full_data)) for chf in handlers
        }

        target = fetchable(
            "testfile.tar.gz",
            uri=["http://example.com/testfile.tar.gz"],
            chksums=chksums,
        )
        fetcher = make_fetcher(distdir)
        partial_path = os.path.join(distdir, "testfile.tar.gz")

        def fake_spawn(cmd, **kwargs):
            # Write partial data (smaller than expected)
            with open(partial_path, "wb") as f:
                f.write(full_data[: len(full_data) // 2])
            return 92

        with mock.patch("pkgcore.fetch.custom.spawn_bash", side_effect=fake_spawn):
            with pytest.raises((errors.FetchFailed, errors.ChksumFailure)):
                fetcher.fetch(target)

        # Partial file should still be present — our fix must not touch it
        assert os.path.exists(partial_path)
