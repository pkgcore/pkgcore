import datetime
import os
import time
from unittest import mock

import pytest

from pkgcore.sync import base, rsync
from pkgcore.sync.tar import tar_syncer


def fake_ips(num):
    """Generate simple IPv4 addresses given the amount to create."""
    return [(None, None, None, None, (".".join(str(x) * 4), 0)) for x in range(num)]


@mock.patch("socket.getaddrinfo", return_value=fake_ips(3))
@mock.patch("pkgcore.sync.base.subprocess.run")
class TestRsyncSyncer:
    _syncer_class = rsync.rsync_syncer

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.repo_path = str(tmp_path / "repo")
        with mock.patch("shutil.which", return_value="rsync"):
            self.syncer = self._syncer_class(
                self.repo_path, "rsync://rsync.gentoo.org/gentoo-portage"
            )

    @mock.patch("shutil.which")
    def test_uri_parse_rsync_missing(self, which, run, getaddrinfo):
        which.return_value = None
        with pytest.raises(base.SyncError):
            self._syncer_class(self.repo_path, "rsync://foon.com/dar")

    @mock.patch("shutil.which")
    def test_uri_parse(self, which, run, getaddrinfo):
        which.side_effect = lambda x: x
        o = self._syncer_class(self.repo_path, "rsync://dar/module")
        assert o.uri == "rsync://dar/module/"
        assert o.rsh is None

        o = self._syncer_class(self.repo_path, "rsync+/bin/sh://dar/module")
        assert o.uri == "rsync://dar/module/"
        assert o.rsh == "/bin/sh"

    def test_successful_sync(self, run, getaddrinfo):
        run.return_value.returncode = 0
        assert self.syncer.sync()
        run.assert_called_once()

    def test_bad_syntax_sync(self, run, getaddrinfo):
        run.return_value.returncode = 1
        with pytest.raises(base.SyncError) as excinfo:
            assert self.syncer.sync()
        assert str(excinfo.value).startswith("rsync command syntax error:")
        run.assert_called_once()

    def test_failed_disk_space_sync(self, run, getaddrinfo):
        run.return_value.returncode = 11
        with pytest.raises(base.SyncError) as excinfo:
            assert self.syncer.sync()
        assert str(excinfo.value) == "rsync ran out of disk space"
        run.assert_called_once()

    def test_retried_sync(self, run, getaddrinfo):
        run.return_value.returncode = 99
        with pytest.raises(base.SyncError) as excinfo:
            assert self.syncer.sync()
        assert str(excinfo.value) == "all attempts failed"
        # rsync should retry every resolved IP related to the sync URI
        assert len(run.mock_calls) == 3

    def test_retried_sync_max_retries(self, run, getaddrinfo):
        run.return_value.returncode = 99
        # generate more IPs than retries
        getaddrinfo.return_value = fake_ips(self.syncer.retries + 1)
        with pytest.raises(base.SyncError) as excinfo:
            assert self.syncer.sync()
        assert str(excinfo.value) == "all attempts failed"
        assert len(run.mock_calls) == self.syncer.retries

    def test_failed_dns_sync(self, run, getaddrinfo):
        getaddrinfo.side_effect = OSError()
        with pytest.raises(base.SyncError) as excinfo:
            assert self.syncer.sync()
        assert str(excinfo.value).startswith("DNS resolution failed")
        run.assert_not_called()


class TestRsyncTimestampSyncer(TestRsyncSyncer):
    _syncer_class = rsync.rsync_timestamp_syncer


@pytest.mark_network
class TestRsyncSyncerReal:
    def test_sync(self, tmp_path):
        # perform a tarball sync for initial week-old base
        path = tmp_path / "repo"
        week_old = datetime.datetime.now() - datetime.timedelta(days=7)
        date_str = week_old.strftime("%Y%m%d")
        syncer = tar_syncer(
            str(path),
            f"http://distfiles.gentoo.org/snapshots/portage-{date_str}.tar.xz",
        )
        assert syncer.sync()
        timestamp = os.path.join(path, "metadata", "timestamp.chk")
        assert os.path.exists(timestamp)
        stat = os.stat(timestamp)

        # run rsync over the unpacked repo tarball to update to the latest tree
        syncer = rsync.rsync_timestamp_syncer(
            str(path), "rsync://rsync.gentoo.org/gentoo-portage"
        )
        assert syncer.sync()
        assert stat != os.stat(timestamp)


@mock.patch("socket.getaddrinfo", return_value=fake_ips(1))
@mock.patch("pkgcore.sync.base.subprocess.run")
class TestRsyncTimestampCheck:
    stamp = "Mon, 28 Sep 2026 00:00:00 +0300\n"

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path):
        self.repo_path = tmp_path / "repo"
        (self.repo_path / "metadata").mkdir(parents=True)
        (self.repo_path / "metadata" / "timestamp.chk").write_text(self.stamp)
        with mock.patch("shutil.which", side_effect=lambda x: f"/bin/{x}"):
            self.syncer = rsync.rsync_timestamp_syncer(
                str(self.repo_path),
                "rsync+ssh://user@example.org/gentoo",
                proxy="proxy:3128",
            )

    def test_check_uses_sync_settings(self, run, getaddrinfo):
        def fake_run(cmd, **kwargs):
            with open(cmd[2], "w") as f:
                f.write(self.stamp)
            return mock.Mock(returncode=0)

        run.side_effect = fake_run
        assert self.syncer.sync()
        # timestamp unchanged: only the timestamp was fetched
        assert run.call_count == 1
        cmd = run.call_args.args[0]
        assert cmd[1].endswith("/gentoo/metadata/timestamp.chk")
        assert cmd[cmd.index("-e") + 1] == "/bin/ssh"
        assert run.call_args.kwargs["env"]["RSYNC_PROXY"] == "proxy:3128"

    def test_failed_check_falls_back_to_full_sync(self, run, getaddrinfo):
        run.side_effect = [mock.Mock(returncode=5), mock.Mock(returncode=0)]
        assert self.syncer.sync()
        assert run.call_count == 2
        cmd = run.call_args.args[0]
        assert cmd[2].rstrip("/") == str(self.repo_path)


class TestCurrentTimestamp:
    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        # a non-UTC local zone, to catch parsing in local time
        monkeypatch.setenv("TZ", "Asia/Jerusalem")
        time.tzset()
        yield
        monkeypatch.undo()
        time.tzset()

    @pytest.mark.parametrize(
        "stamp",
        (
            "Mon, 28 Sep 2026 10:00:00 +0000",
            "Mon, 28 Sep 2026 12:30:00 +0230",
            "Mon, 28 Sep 2026 05:00:00 -0500",
            "Mon, 28 Sep 2026 10:00:00 -0000",
        ),
    )
    def test_offsets(self, tmp_path, stamp):
        path = tmp_path / "timestamp.chk"
        path.write_text(stamp + "\n")
        expected = datetime.datetime(2026, 9, 28, 10, tzinfo=datetime.UTC).timestamp()
        assert rsync.rsync_timestamp_syncer.current_timestamp(None, path) == expected

    def test_malformed(self, tmp_path):
        path = tmp_path / "timestamp.chk"
        path.write_text("not a date\n")
        assert rsync.rsync_timestamp_syncer.current_timestamp(None, path) is None
