"""
fetcher class that pulls files via executing another program to do the fetching
"""

__all__ = ("MalformedCommand", "fetcher",)

import os

from snakeoil.osutils import ensure_dirs, pjoin
from snakeoil.process.spawn import is_userpriv_capable, spawn_bash

from ..config.hint import ConfigHint
from ..os_data import portage_gid, portage_uid
from . import base, errors, fetchable


class MalformedCommand(errors.FetchError):

    def __init__(self, command):
        super().__init__(f'fetchcommand is malformed: {command}')
        self.command = command


class fetcher(base.fetcher):

    pkgcore_config_type = ConfigHint(
        {'userpriv': 'bool', 'required_chksums': 'list',
         'distdir': 'str', 'command': 'str', 'resume_command': 'str'},
        allow_unknowns=True)

    def __init__(self, distdir, command, resume_command=None,
                 required_chksums=None, userpriv=True, attempts=10,
                 readonly=False, **extra_env):
        """
        :param distdir: directory to download files to
        :type distdir: string
        :param command: shell command to execute to fetch a file
        :type command: string
        :param resume_command: if not None, command to use for resuming-
            if None, command is reused
        :param required_chksums: if None, all chksums must be verified,
            else only chksums listed
        :type required_chksums: None or sequence
        :param userpriv: depriv for fetching?
        :param attempts: max number of attempts before failing the fetch
        :param readonly: controls whether fetching is allowed
        """
        super().__init__()
        self.distdir = distdir
        if required_chksums is not None:
            required_chksums = [x.lower() for x in required_chksums]
        else:
            required_chksums = []
        if len(required_chksums) == 1 and required_chksums[0] == "all":
            self.required_chksums = None
        else:
            self.required_chksums = required_chksums

        def rewrite_command(string):
            new_command = string.replace("${DISTDIR}", self.distdir)
            new_command = new_command.replace("$DISTDIR", self.distdir)
            new_command = new_command.replace("${URI}", "%(URI)s")
            new_command = new_command.replace("$URI", "%(URI)s")
            new_command = new_command.replace("${FILE}", "%(FILE)s")
            new_command = new_command.replace("$FILE", "%(FILE)s")
            if new_command == string:
                raise MalformedCommand(string)
            try:
                new_command % {"URI": "blah", "FILE": "blah"}
            except KeyError as k:
                raise MalformedCommand(f"{command}: unexpected key {k.args[0]}")
            return new_command

        self.command = rewrite_command(command)
        if resume_command is None:
            self.resume_command = self.command
        else:
            self.resume_command = rewrite_command(resume_command)

        self.attempts = attempts
        self.userpriv = userpriv
        self.readonly = readonly
        self.extra_env = extra_env

    def fetch(self, target):
        """Fetch a file.

        :type target: :obj:`pkgcore.fetch.fetchable` instance
        :return: None if fetching failed,
            else on disk location of the copied file
        """
        if not isinstance(target, fetchable):
            raise TypeError(
                f"target must be fetchable instance/derivative: {target}")

        kw = {"mode": 0o775}
        if self.readonly:
            kw["mode"] = 0o555
        if self.userpriv:
            kw["gid"] = portage_gid
        kw["minimal"] = True
        if not ensure_dirs(self.distdir, **kw):
            raise errors.DistdirPerms(
                self.distdir, "if userpriv, uid must be %i, gid must be %i. "
                "if not readonly, directory must be 0775, else 0555" % (
                    portage_uid, portage_gid))

        path = pjoin(self.distdir, target.filename)
        uris = iter(target.uri)
        last_exc = RuntimeError("fetching failed for an unknown reason")
        spawn_opts = {'umask': 0o002, 'env': self.extra_env}
        if self.userpriv and is_userpriv_capable():
            spawn_opts.update({"uid": portage_uid, "gid": portage_gid})

        for _attempt in range(self.attempts):
            try:
                self._verify(path, target)
                return path
            except errors.MissingDistfile as e:
                command = self.command
                last_exc = e
            except errors.ChksumFailure:
                raise
            except errors.FetchFailed as e:
                last_exc = e
                if not e.resumable:
                    try:
                        os.unlink(path)
                        command = self.command
                    except OSError as e:
                        raise errors.UnmodifiableFile(path, e) from e
                else:
                    command = self.resume_command
            # Note we're not even checking the results, the verify portion of
            # the loop handles this. In other words, don't trust the external
            # fetcher's exit code, trust our chksums instead.
            try:
                spawn_bash(
                    command % {"URI": next(uris), "FILE": target.filename},
                    **spawn_opts)
            except StopIteration:
                raise errors.FetchFailed(
                    target.filename, "ran out of urls to fetch from")
        else:
            raise last_exc

    def get_path(self, fetchable):
        path = pjoin(self.distdir, fetchable.filename)
        if self._verify(path, fetchable) is None:
            return path
        return None

    def get_storage_path(self):
        return self.distdir
