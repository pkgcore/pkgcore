import argparse
import itertools
import os
import shlex
import shutil
import stat
import subprocess
import sys

from snakeoil.compatibility import IGNORED_EXCEPTIONS
from snakeoil.demandload import demandload
from snakeoil.iterables import partition
from snakeoil.osutils import pjoin

from pkgcore.exceptions import PkgcoreException, PkgcoreUserException

demandload(
    'grp',
    'operator:itemgetter',
    'pwd',
)


class IpcError(PkgcoreException):
    """Generic IPC errors."""

    def __init__(self, msg='', code=1):
        self.msg = msg
        self.code = code
        self.ret = f'{code}\x07{msg}'


class IpcInternalError(IpcError):
    """IPC errors related to internal bugs."""


class IpcCommandError(IpcError, PkgcoreUserException):
    """IPC errors related to parsing arguments or running the command."""


class UnknownOptions(IpcCommandError):
    """Unknown options passed to IPC command."""

    def __init__(self, options):
        super().__init__(f"unknown options: {', '.join(map(repr, options))}")


class ArgumentParser(argparse.ArgumentParser):
    """Raise IPC exception for argparse errors.

    Otherwise standard argparse prints the parser usage then outputs the error
    message to stderr.
    """

    def error(self, msg):
        raise IpcCommandError(msg)


class IpcCommand(object):
    """Commands sent from the bash side of the ebuild daemon to run."""

    def __init__(self, op):
        self.op = op
        self.observer = self.op.observer
        self._helper = self.__class__.__name__.lower()
        self.opts = argparse.Namespace()

    def __call__(self, ebd):
        self.ebd = ebd
        options = shlex.split(self.read())
        args = self.read().strip('\0').split('\0')
        ret = 0

        try:
            self.parse_options(options)
            self.finalize_args(args)
            self.run()
        except IGNORED_EXCEPTIONS:
            raise
        except IpcCommandError:
            raise
        except Exception as e:
            raise IpcInternalError(f'internal python failure') from e

        # return completion status to the bash side
        self.write(ret)

    def parse_options(self, opts):
        """Parse the args passed from the bash side."""
        opts, unknown = self.parser.parse_known_args(opts, namespace=self.opts)
        if unknown:
            raise UnknownOptions(unknown)

    def finalize_args(self, args):
        """Finalize the options and arguments for the IPC command."""

    def run(self):
        """Run the requested IPC command."""
        raise NotImplementedError

    def read(self):
        """Read a line from the ebuild daemon."""
        return self.ebd.read().strip()

    def write(self, data):
        """Write data to the ebuild daemon.

        Args:
            data: data to be sent to the bash side
        """
        self.ebd.write(data)

    def warn(self, msg):
        """Output warning message.

        Args:
            msg: message to be output
        """
        self.observer.warn(f'{self._helper}: {msg}')
        self.observer.flush()


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


def command_options(s):
    """Split string of command line options into list."""
    return shlex.split(s)


class _InstallWrapper(IpcCommand):
    """Python wrapper for commands using `install`."""

    parser = ArgumentParser(add_help=False)
    parser.add_argument('--cwd', required=True)
    parser.add_argument('--dest', required=True)
    parser.add_argument('--insoptions', default='', type=command_options)
    parser.add_argument('--diroptions', default='', type=command_options)
    parser.add_argument('--recursive', action='store_true')

    # supported install options
    install_parser = ArgumentParser(add_help=False)
    install_parser.add_argument('-g', '--group', default=-1, type=_parse_group)
    install_parser.add_argument('-o', '--owner', default=-1, type=_parse_user)
    install_parser.add_argument('-m', '--mode', default=0o755, type=_parse_mode)
    install_parser.add_argument('-p', '--preserve-timestamps', action='store_true')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.insoptions = argparse.Namespace()
        self.diroptions = argparse.Namespace()
        # default to python-based install cmds
        self.install = self._install
        self.install_dirs = self._install_dirs

    def parse_options(self, opts):
        super().parse_options(opts)
        if not self._parse_install_options(self.opts.insoptions, self.insoptions):
            self.install = self._install_cmd
        if not self._parse_install_options(self.opts.diroptions, self.diroptions):
            self.install_dirs = self._install_dirs_cmd

    def _parse_install_options(self, options, namespace):
        """Parse install command options.

        Args:
            options: list of options to parse
            namespace: argparse namespace to populate
        Returns:
            True when all options are handled,
            otherwise False if unknown/unhandled options exist.
        """
        opts, unknown = self.install_parser.parse_known_args(options, namespace=namespace)
        if unknown or opts.mode is None:
            msg = "falling back to 'install'"
            if unknown:
                msg += f": unhandled options: {' '.join(map(repr, unknown))}"
            self.warn(msg)
            return False
        return True

    def finalize_args(self, args):
        if not args:
            raise IpcCommandError('missing targets')
        self.targets = args
        self.target_dir = pjoin(self.op.ED, self.opts.dest.lstrip(os.path.sep))

    def run(self):
        os.chdir(self.opts.cwd)
        self.install_dirs([self.target_dir])
        self._install_targets(x.rstrip(os.path.sep) for x in self.targets)

    def _install_targets(self, targets):
        """Install targets.

        Args:
            targets: files/symlinks/dirs/etc to install
        """
        files, dirs = partition(targets, predicate=os.path.isdir)
        if self.opts.recursive:
            self._install_from_dirs(dirs)
        self._install_files((f, self.target_dir) for f in files)

    def _install_files(self, files):
        """Install files into a given directory.

        Args:
            files: iterable of (path, target dir) tuples of files to install
        """
        self.install(files)

    def _install_from_dirs(self, dirs):
        """Install all targets under given directories.

        Args:
            dirs: iterable of directories to install from
        """
        def scan_dirs(paths):
            for d in paths:
                dest_dir = pjoin(self.target_dir, os.path.basename(d))
                yield True, dest_dir
                for dirpath, dirnames, filenames in os.walk(d):
                    for dirname in dirnames:
                        source_dir = pjoin(dirpath, dirname)
                        relpath = os.path.relpath(source_dir, self.opts.cwd)
                        if os.path.islink(source_dir):
                            yield False, (relpath, dest_dir)
                        else:
                            yield True, pjoin(self.target_dir, relpath)
                    yield from (
                        (False, (os.path.relpath(pjoin(dirpath, f), self.opts.cwd), dest_dir))
                        for f in filenames)

        # determine all files and dirs under target directories and install them
        files, dirs = partition(scan_dirs(dirs), predicate=itemgetter(0))
        self.install_dirs(path for _, path in dirs)
        self._install_files(path for _, path in files)

    @staticmethod
    def _set_attributes(opts, path):
        """Set file attributes on a given path.

        Args:
            path: file/directory path
        """
        if opts.owner != -1 or opts.group != -1:
            os.lchown(path, opts.owner, opts.group)
        if opts.mode is not None:
            os.chmod(path, opts.mode)

    @staticmethod
    def _set_timestamps(source_stat, dest):
        """Apply timestamps from source_stat to dest.

        Args:
            source_stat: stat result for the source file
            dest: path to the dest file
        """
        os.utime(dest, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))

    def _is_install_allowed(self, source, source_stat, dest):
        """Determine if installing source into dest should work.

        This aims to aid compatibility with the `install` command.

        Args:
            source: path to the source file
            source_stat: stat result for the source file, using stat()
                rather than lstat(), in order to match the `install`
                command
            dest: path to the dest file
        Raises:
            IpcCommandError on failure
        Returns:
            True if the install should succeed
        """
        # matching `install` command, use stat() for source and lstat() for dest
        try:
            dest_lstat = os.lstat(dest)
        except FileNotFoundError:
            # installing file to a new path
            return True
        except OSError as e:
            raise IpcCommandError(f'cannot stat {dest!r}: {e.strerror}')

        # installing symlink
        if stat.S_ISLNK(dest_lstat.st_mode):
            return True

        # source file and dest file are different
        if not os.path.samestat(source_stat, dest_lstat):
            return True

        # installing hardlink if source and dest are different
        if (dest_lstat.st_nlink > 1 and os.path.realpath(source) != os.path.realpath(dest)):
            return True

        raise IpcCommandError(f'{source!r} and {dest!r} are identical')

    def _install(self, files):
        """Install files.

        Args:
            files: iterable of (path, target dir) tuples of files to install
        Raises:
            IpcCommandError on failure
        """
        for f, dest_dir in files:
            dest = pjoin(dest_dir, os.path.basename(f))
            try:
                sstat = os.stat(f)
            except OSError as e:
                raise IpcCommandError(f'cannot stat {f!r}: {e.strerror}')
            self._is_install_allowed(f, sstat, dest)

            # matching `install` command, remove dest before file install
            try:
                os.unlink(dest)
            except FileNotFoundError:
                pass
            except OSError as e:
                raise IpcCommandError(f'failed removing file: {dest!r}: {e.strerror}')

            try:
                shutil.copyfile(f, dest)
                if self.opts.insoptions:
                    self._set_attributes(self.insoptions, dest)
                if self.insoptions.preserve_timestamps:
                    self._set_timestamps(sstat, dest)
            except OSError as e:
                raise IpcCommandError(f'failed copying file: {f!r} to {dest_dir!r}: {e.strerror}')

    def _install_cmd(self, files):
        """Install files using `install` command.

        Args:
            files: iterable of (path, target dir) tuples of files to install
        Raises:
            IpcCommandError on failure
        """
        files = sorted(files, key=itemgetter(1))
        for dest_dir, files_group in itertools.groupby(files, itemgetter(1)):
            paths = list(path for path, _ in files_group)
            command = ['install'] + self.opts.insoptions + paths + [dest_dir]
            try:
                subprocess.run(command, check=True, stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as e:
                raise IpcCommandError(e.stderr.decode())

    def _install_dirs(self, dirs):
        """Create directories.

        Args:
            dirs: iterable of paths where directories should be created
        Raises:
            IpcCommandError on failure
        """
        try:
            for d in dirs:
                os.makedirs(d, exist_ok=True)
                if self.opts.diroptions:
                    self._set_attributes(self.diroptions, d)
        except OSError as e:
            raise IpcCommandError(f'failed creating dir: {dest!r}: {e.strerror}')

    def _install_dirs_cmd(self, dirs):
        """Create directories using `install` command.

        Args:
            dirs: iterable of paths where directories should be created
        Raises:
            IpcCommandError on failure
        """
        if not isinstance(dirs, list):
            dirs = list(dirs)
        command = ['install', '-d'] + self.opts.diroptions + dirs
        try:
            subprocess.run(command, check=True, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            raise IpcCommandError(e.stderr.decode())

    def install_symlinks(self, symlinks):
        """Install iterable of symlinks.

        Args:
            symlinks: iterable of (path, target dir) tuples of symlinks to install
        Raises:
            IpcCommandError on failure
        """
        try:
            for symlink, dest_dir in symlinks:
                dest = pjoin(dest_dir, os.path.basename(symlink))
                try:
                    os.unlink(dest)
                except IsADirectoryError:
                    shutil.rmtree(dest, ignore_errors=True)
                os.symlink(os.readlink(symlink), dest)
        except OSError as e:
            raise IpcCommandError(
                f'failed creating symlink: {symlink!r} -> {dest!r}: {e.strerror}')


class Doins(_InstallWrapper):
    """Python wrapper for doins."""

    def finalize_args(self, args):
        super().finalize_args(args)
        self.allow_symlinks = self.op.pkg.eapi.options.doins_allow_symlinks

    def _install_files(self, files):
        if self.allow_symlinks:
            files, symlinks = partition(files, predicate=lambda x: os.path.islink(x[0]))
            self.install_symlinks(symlinks)
        self.install(files)


class Dodoc(_InstallWrapper):
    """Python wrapper for dodoc."""

    def finalize_args(self, args):
        super().finalize_args(args)
        self.allow_recursive = self.op.pkg.eapi.options.dodoc_allow_recursive

    def _install_targets(self, targets):
        files, dirs = partition(targets, predicate=os.path.isdir)
        dirs = list(dirs)
        if dirs:
            if self.opts.recursive and self.allow_recursive:
                self._install_from_dirs(dirs)
            else:
                missing_option = ', missing -r option?' if self.allow_recursive else ''
                raise IpcCommandError(f'{dirs[0]} is a directory{missing_option}')
        self._install_files((f, self.target_dir) for f in files)
