# -*- coding: utf-8 -*-

__all__ = ("git_svn_syncer",)

import os

from . import base


class git_svn_syncer(base.VcsSyncer):

    binary = "git"

    supported_uris = (
        ('git+svn://', 10),
        ('git+svn+', 10),
    )

    @classmethod
    def is_usable_on_filepath(cls, path):
        git_svn_path = os.path.join(path, '.git', 'svn')
        if cls.disabled or not os.path.isdir(git_svn_path):
            return None
        return (cls._rewrite_uri_from_stat(git_svn_path, "git+svn://"),)

    @staticmethod
    def parse_uri(raw_uri):
        if not raw_uri.startswith("git+svn+") and not raw_uri.startswith("git+svn://"):
            raise base.UriError(
                raw_uri, "doesn't start with git+svn+ nor git+svn://")
        if raw_uri.startswith("git+svn+"):
            if raw_uri.startswith("git+svn+:"):
                raise base.UriError(
                    raw_uri, "need to specify the sub protocol if using git+svn+")
            return raw_uri[8:]
        return raw_uri[4:]

    def _initial_pull(self):
        return [self.binary_path, "svn", "clone", self.uri, self.basedir]

    def _update_existing(self):
        return [self.binary_path, "svn", "rebase"]
