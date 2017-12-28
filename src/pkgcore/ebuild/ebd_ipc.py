import argparse
import os

from snakeoil.demandload import demandload
from snakeoil.osutils import pjoin

demandload(
    'grp',
    'pwd',
)


class IpcCommandError(Exception):
    """IPC errors related to parsing arguments or running the command."""


class ArgumentParser(argparse.ArgumentParser):
    """Raise IPC exception for argparse errors.

    Otherwise standard argparse prints the parser usage then outputs the error
    message to stderr.
    """

    def error(self, message):
        raise IpcCommandError(message)


class IpcCommand(object):
    """Commands sent from the bash side of the ebuild daemon to run."""

    def __init__(self, op, async=False):
        self.op = op
        self.async = async

    def __call__(self, ebd, numargs_str=None):
        self.ebd = ebd
        cmdargs = {}
        if numargs_str is not None:
            numargs = int(numargs_str.split('=', 1)[1])
            for x in range(numargs):
                k, v = self.read().rstrip('\n').split('=', 1)
                cmdargs[k] = v

        try:
            self.parse_args(**cmdargs)
            ret = self.run()
        except IpcCommandError as e:
            ret = e

        # return completion status to the bash side if running in synchronous mode
        if not self.async:
            self.write(ret)

    def parse_args(self, **kwargs):
        """Parse the args passed from the bash side."""
        pass

    def run(self):
        """Run the requested IPC command."""
        raise NotImplementedError()

    def read(self):
        """Read from the ebuild daemon."""
        return self.ebd.read()

    def write(self, s):
        """Write data to the ebuild daemon."""
        self.ebd.write(s)


def _parse_group(group):
    try:
        return grp.getgrnam(group).gr_gid
    except KeyError:
            pass
    return int(group)


def _parse_user(user):
    try:
        return pwd.getpwnam(user).pw_uid
    except KeyError:
        pass
    return int(user)


def _parse_mode(mode):
    try:
        return int(mode, 8)
    except ValueError:
        return None


class Doins(IpcCommand):
    """Python wrapper for doins."""

    parser = ArgumentParser(add_help=False)
    parser.add_argument('-r', action='store_true', dest='recursive')
    # supported install options
    parser.add_argument('-g', '--group', default=-1, type=_parse_group)
    parser.add_argument('-o', '--owner', default=-1, type=_parse_user)
    parser.add_argument('-m', '--mode', default=0o755, type=_parse_mode)
    # specified targets to install
    parser.add_argument('targets', nargs=argparse.REMAINDER)

    def parse_args(self, dest='', args=''):
        self.opts, unknown = self.parser.parse_known_args([x for x in args.split('\x07') if x])
        # add args with hyphen prefixes that aren't known options to target list
        self.opts.targets.extend(unknown)
        if not self.opts.targets:
            raise IpcCommandError('missing targets')
        self.dest = pjoin(self.op.ED, dest).rstrip(os.path.sep)

    def run(self):
        # dirs = set()
        # for target in targets:
        #     if os.path.isdir(pjoin(self.op.env["WORKDIR"], target)):
        #         os.mkdir(pjoin(self.op.ED, target))

        return 0
