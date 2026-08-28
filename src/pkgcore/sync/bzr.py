__all__ = ("bzr_syncer",)

import os
import subprocess

from . import base


class bzr_syncer(base.VcsSyncer):
    binary = "bzr"

    supported_uris = (("bzr+", 5),)

    @classmethod
    def is_usable_on_filepath(cls, path):
        bzr_path = os.path.join(path, ".bzr")
        if cls.disabled or not os.path.isdir(bzr_path):
            return None
        ret = subprocess.run(
            [cls.binary, "info", path], capture_output=True, text=True, check=False
        )
        if ret.returncode != 0:
            # should alert the user somehow
            return None
        for line in ret.stdout.splitlines():
            line = line.strip().split(":", 1)
            if len(line) != 2:
                continue
            if line[0] == "parent branch":
                uri = f"bzr+{line[1].strip()}"
                return (cls._rewrite_uri_from_stat(bzr_path, uri),)
        return None

    @staticmethod
    def parse_uri(raw_uri):
        if not raw_uri.startswith("bzr+"):
            raise base.UriError(raw_uri, "doesn't start with bzr+")
        return raw_uri[4:]

    def _initial_pull(self):
        return [self.binary_path, "branch", self.uri, self.basedir]

    def _update_existing(self):
        return [self.binary_path, "pull", self.uri]
