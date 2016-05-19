# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
fetcher class that pulls files via executing another program to do the fetching
"""

__all__ = ("MalformedCommand", "fetcher",)

import os
import sys

from snakeoil.osutils import ensure_dirs, pjoin
from snakeoil.compatibility import raise_from
from snakeoil.demandload import demandload

from pkgcore.spawn import spawn_bash, is_userpriv_capable
from pkgcore.os_data import portage_uid, portage_gid
from pkgcore.fetch import errors, base, fetchable
from pkgcore.config import ConfigHint

demandload("pkgcore.log:logger")

class MalformedCommand(errors.base):

    def __init__(self, command):
        errors.base.__init__(self, "fetchcommand is malformed: %s" % (command,))
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
        base.fetcher.__init__(self)
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
                raise MalformedCommand("%s: unexpected key %s" % (command, k.args[0]))
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
        """
        fetch a file

        :type target: :obj:`pkgcore.fetch.fetchable` instance
        :return: None if fetching failed,
            else on disk location of the copied file
        """

        if not isinstance(target, fetchable):
            raise TypeError(
                "target must be fetchable instance/derivative: %s" % target)

        kw = {"mode": 0775}
        if self.readonly:
            kw["mode"] = 0555
        if self.userpriv:
            kw["gid"] = portage_gid
        kw["minimal"] = True
        if not ensure_dirs(self.distdir, **kw):
            raise errors.distdirPerms(
                self.distdir, "if userpriv, uid must be %i, gid must be %i. "
                "if not readonly, directory must be 0775, else 0555" % (
                    portage_uid, portage_gid))

        fp = pjoin(self.distdir, target.filename)
        filename = os.path.basename(fp)

        if self.userpriv and is_userpriv_capable():
            extra = {"uid": portage_uid, "gid": portage_gid}
        else:
            extra = {}
        extra["umask"] = 0002
        extra["env"] = self.extra_env
        command = self.command
        for attempt, uri in enumerate(iter(target.uri)):
            if (attempt + 1) > self.attempts: break
            try:
                spawn_bash(command % {"URI": uri, "FILE": filename}, **extra)
                self._verify(fp, target)
                return fp
            except (errors.MissingDistfile,\
                    errors.FetchFailed,\
                    errors.RequiredChksumDataMissing
                    ) as e:
                logger.error(str(e), exc_info=1)
                if not e.resumable:
                    try:
                        os.unlink(fp)
                        command = self.command
                    except OSError as oe:
                        logger.error(str(oe), exc_info=1)
                        logger.error('Unable to unlink file: %s\n' % fp)
                else:
                    command = self.resume_command
            except Exception as e:
                logger.error("spawn_bash error occured: %s\n" % e)
        raise errors.FetchFailed(fp, "Ran out of urls to fetch from")

    def get_path(self, fetchable):
        fp = pjoin(self.distdir, fetchable.filename)
        if self._verify(fp, fetchable) is None:
            return fp
        return None

    def get_storage_path(self):
        return self.distdir
