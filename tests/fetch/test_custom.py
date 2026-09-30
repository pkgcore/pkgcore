import os
import subprocess
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


def chksums_for(data: bytes):
    from snakeoil import data_source
    from snakeoil.chksum import get_handlers

    handlers = get_handlers()
    return {chf: handlers[chf](data_source.data_source(data)) for chf in handlers}


def partial_content(path: str):
    with open(path, "wb") as f:
        f.write(b"partial download content")


class TestFetch:
    """Tests for fetch() when the fetchable has no checksums (new manifest generation)."""

    @mock.patch("pkgcore.fetch.custom.subprocess.run")
    def test_failed_fetch_deletes_partial_file(self, run, distdir: str):
        """Non-zero fetcher exit with no checksums must clean up the partial file."""
        target = fetchable(
            "testfile.tar.gz",
            uri=["http://example.com/testfile.tar.gz"],
            chksums={},
        )
        fetcher = make_fetcher(distdir)
        partial_path = os.path.join(distdir, "testfile.tar.gz")

        def fake_run(cmd, **kwargs):
            partial_content(partial_path)
            return subprocess.CompletedProcess(cmd, 92)  # HTTP/2 stream error

        run.side_effect = fake_run
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

        def fake_run(cmd, **kwargs):
            partial_content(expected_path)
            return subprocess.CompletedProcess(cmd, 0)

        with mock.patch("pkgcore.fetch.custom.subprocess.run", side_effect=fake_run):
            result = fetcher.fetch(target)

        assert result == expected_path
        assert os.path.exists(expected_path)

    @mock.patch(
        "pkgcore.fetch.custom.subprocess.run",
        return_value=subprocess.CompletedProcess([], 92),
    )
    def test_failed_fetch_no_partial_file_left(self, run, distdir: str):
        """Non-zero exit when no file was written should not raise OSError."""
        target = fetchable(
            "testfile.tar.gz",
            uri=["http://example.com/testfile.tar.gz"],
            chksums={},
        )
        fetcher = make_fetcher(distdir)

        with pytest.raises(errors.FetchFailed):
            fetcher.fetch(target)

    @mock.patch("pkgcore.fetch.custom.subprocess.run")
    def test_failed_fetch_keeps_partial_for_resume(self, run, distdir: str):
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

        def fake_run(cmd, **kwargs):
            # Write partial data (smaller than expected)
            with open(partial_path, "wb") as f:
                f.write(full_data[: len(full_data) // 2])
            return subprocess.CompletedProcess(cmd, 92)

        run.side_effect = fake_run

        with pytest.raises((errors.FetchFailed, errors.ChksumFailure)):
            fetcher.fetch(target)

        # Partial file should still be present — our fix must not touch it
        assert os.path.exists(partial_path)

    @pytest.mark.parametrize("attempts", (1, 2))
    def test_last_attempt_is_verified(self, distdir: str, attempts):
        """A download that only succeeds on the final attempt still counts."""
        target = fetchable(
            "testfile.tar.gz",
            uri=[f"http://example.com/{i}" for i in range(attempts)],
            chksums={},
        )
        fetcher = make_fetcher(distdir, attempts=attempts)
        expected_path = os.path.join(distdir, "testfile.tar.gz")
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if len(calls) < attempts:
                return subprocess.CompletedProcess(cmd, 1)
            partial_content(expected_path)
            return subprocess.CompletedProcess(cmd, 0)

        with mock.patch("pkgcore.fetch.custom.subprocess.run", side_effect=fake_run):
            assert fetcher.fetch(target) == expected_path
        assert len(calls) == attempts


class TestCommand:
    def test_placeholders_are_rewritten(self, distdir: str):
        fetcher = custom.fetcher(
            distdir=distdir,
            command="wget ${URI} -O ${DISTDIR}/${FILE}",
            resume_command="wget -c $URI -O $DISTDIR/$FILE",
        )
        assert fetcher.command == f"wget %(URI)s -O {distdir}/%(FILE)s"
        assert fetcher.resume_command == f"wget -c %(URI)s -O {distdir}/%(FILE)s"

    def test_resume_defaults_to_command(self, distdir: str):
        fetcher = custom.fetcher(distdir=distdir, command="wget ${URI}")
        assert fetcher.resume_command == fetcher.command

    @pytest.mark.parametrize(
        "command", ("wget http://example.org/x", "wget ${URI} %(OTHER)s")
    )
    def test_malformed(self, distdir: str, command):
        with pytest.raises(custom.MalformedCommand):
            custom.fetcher(distdir=distdir, command=command)


class TestFetchAttempts:
    data = b"complete file content for checksum"

    def mk_fetcher(self, distdir, attempts=3):
        return custom.fetcher(
            distdir=distdir,
            command="fetch ${URI} ${FILE}",
            resume_command="resume ${URI} ${FILE}",
            userpriv=False,
            attempts=attempts,
        )

    def target(self, *uris):
        return fetchable("file.tar.gz", uri=list(uris), chksums=chksums_for(self.data))

    def test_partial_download_is_resumed(self, distdir: str):
        path = os.path.join(distdir, "file.tar.gz")
        commands = []

        def fake_run(cmd, **kwargs):
            commands.append(cmd[-1])
            with open(path, "wb") as f:
                f.write(
                    self.data[: len(self.data) // 2 if len(commands) == 1 else None]
                )
            return subprocess.CompletedProcess(cmd, 0)

        target = self.target("http://a.example.org/f", "http://b.example.org/f")
        with mock.patch("pkgcore.fetch.custom.subprocess.run", side_effect=fake_run):
            assert self.mk_fetcher(distdir).fetch(target) == path
        assert commands[0].startswith("fetch http://a.example.org/f")
        assert commands[1].startswith("resume http://b.example.org/f")

    def test_runs_out_of_uris(self, distdir: str):
        target = self.target("http://a.example.org/f")
        with (
            mock.patch(
                "pkgcore.fetch.custom.subprocess.run",
                return_value=subprocess.CompletedProcess([], 1),
            ) as run,
            pytest.raises(errors.FetchFailed, match="ran out of urls"),
        ):
            self.mk_fetcher(distdir).fetch(target)
        assert run.call_count == 1

    def test_corrupt_existing_file_is_not_refetched(self, distdir: str):
        with open(os.path.join(distdir, "file.tar.gz"), "wb") as f:
            f.write(b"x" * len(self.data))
        target = self.target("http://a.example.org/f")
        with (
            mock.patch("pkgcore.fetch.custom.subprocess.run") as run,
            pytest.raises(errors.ChksumFailure),
        ):
            self.mk_fetcher(distdir).fetch(target)
        run.assert_not_called()

    def test_existing_valid_file_is_not_refetched(self, distdir: str):
        path = os.path.join(distdir, "file.tar.gz")
        with open(path, "wb") as f:
            f.write(self.data)
        with mock.patch("pkgcore.fetch.custom.subprocess.run") as run:
            assert self.mk_fetcher(distdir).fetch(self.target("http://a/f")) == path
        run.assert_not_called()

    def test_rejects_non_fetchables(self, distdir: str):
        with pytest.raises(TypeError):
            self.mk_fetcher(distdir).fetch("file.tar.gz")
