# -*- coding: utf-8 -*-
# Copyright: 2015 Michał Górny <mgorny@gentoo.org>
# License: GPL2/BSD

__all__ = ("git_svn_syncer",)

import os

from pkgcore.sync import base


class git_svn_syncer(base.dvcs_syncer):

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
            raise base.uri_exception(
                raw_uri, "doesn't start with git+svn+ nor git+svn://")
        if raw_uri.startswith("git+svn+"):
            if raw_uri.startswith("git+svn+:"):
                raise base.uri_exception(
                    raw_uri, "need to specify the sub protocol if using git+svn+")
            return raw_uri[8:]
        return raw_uri[4:]

    def __init__(self, basedir, uri, **kwargs):
        uri = self.parse_uri(uri)
        base.dvcs_syncer.__init__(self, basedir, uri, **kwargs)

    def _initial_pull(self):
        return [self.binary_path, "svn", "clone", self.uri, self.basedir]

    def _update_existing(self):
        return [self.binary_path, "svn", "rebase"]
