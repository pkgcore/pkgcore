# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
fetcher class that pulls files via executing another program to do the fetching
"""

import os
from pkgcore.spawn import spawn_bash, userpriv_capable
from pkgcore.os_data import portage_uid, portage_gid
from pkgcore.fs.util import ensure_dirs
from pkgcore.fetch import errors, base, fetchable
from pkgcore.config import ConfigHint

class MalformedCommand(errors.base):

    def __init__(self, command):
        errors.base.__init__(self,
                             "fetchcommand is malformed: %s" % (command,))
        self.command = command


class fetcher(base.fetcher):

    pkgcore_config_type = ConfigHint(
        {'userpriv': 'bool', 'required_chksums': 'list',
         'distdir': 'str', 'command': 'str', 'resume_command': 'str'})

    def __init__(self, distdir, command, resume_command=None,
                 required_chksums=None, userpriv=True, attempts=10,
                 readonly=False):
        """
        @param distdir: directory to download files to
        @type distdir: string
        @param command: shell command to execute to fetch a file
        @type command: string
        @param resume_command: if not None, command to use for resuming-
            if None, command is reused
        @param required_chksums: if None, all chksums must be verified,
            else only chksums listed
        @type required_chksums: None or sequence
        @param userpriv: depriv for fetching?
        @param attempts: max number of attempts before failing the fetch
        @param readonly: controls whether fetching is allowed
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
            if new_command == string:
                raise MalformedCommand(string)
            return new_command

        self.command = rewrite_command(command)
        if resume_command is None:
            self.resume_command = self.command
        else:
            self.resume_command = rewrite_command(resume_command)

        self.attempts = attempts
        self.userpriv = userpriv
        kw = {"mode":0775}
        if readonly:
            kw["mode"] = 0555
        if userpriv:
            kw["gid"] = portage_gid
        kw["minimal"] = True
        if not ensure_dirs(self.distdir, **kw):
            raise errors.distdirPerms(
                self.distdir, "if userpriv, uid must be %i, gid must be %i. "
                "if not readonly, directory must be 0775, else 0555" % (
                    portage_uid, portage_gid))


    def fetch(self, target):
        """
        fetch a file

        @type target: L{pkgcore.fetch.fetchable} instance
        @return: None if fetching failed,
            else on disk location of the copied file
        """


        if not isinstance(target, fetchable):
            raise TypeError(
                "target must be fetchable instance/derivative: %s" % target)

        fp = os.path.join(self.distdir, target.filename)

        uri = iter(target.uri)
        if self.userpriv and userpriv_capable:
            extra = {"uid":portage_uid, "gid":portage_gid}
        else:
            extra = {}
        attempts = self.attempts
        try:
            while attempts >= 0:
                c = self._verify(fp, target)
                if c == 0:
                    return fp
                elif c > 0:
                    try:
                        os.unlink(fp)
                        command = self.command
                    except OSError, oe:
                        raise errors.UnmodifiableFile(fp, oe)
                else:
                    command = self.resume_command

                # yeah, it's funky, but it works.
                if attempts > 0:
                    u = uri.next()
                    # note we're not even checking the results. the
                    # verify portion of the loop handles this. iow,
                    # don't trust their exit code. trust our chksums
                    # instead.
                    spawn_bash(command % {"URI":u}, **extra)
                attempts -= 1

        except StopIteration:
            # ran out of uris
            return None

        return None

