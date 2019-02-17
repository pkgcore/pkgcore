import argparse
import os
import shlex
import shutil
import stat
import subprocess
import sys

from snakeoil.compatibility import IGNORED_EXCEPTIONS
from snakeoil.demandload import demandload
from snakeoil.osutils import pjoin

demandload(
    'grp',
    'pwd',
)


class IpcCommandError(Exception):
    """IPC errors related to parsing arguments or running the command."""

    def __init__(self, msg='', code=1):
        self.msg = msg
        self.code = code
        self.ret = f'{code}\x07{msg}'


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
            raise IpcCommandError(
                f'internal python failure (use --debug to see traceback)')

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
            data: Data to be sent to the bash side.
        """
        self.ebd.write(data)

    def warn(self, msg):
        """Output warning message.

        Args:
            msg: Message to be output.
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
        self.install_dir = self._install_dir

    def parse_options(self, opts):
        super().parse_options(opts)
        if not self._parse_install_options(self.opts.insoptions, self.insoptions):
            self.install = self._install_cmd
        if not self._parse_install_options(self.opts.diroptions, self.diroptions):
            self.install_dir = self._install_dir_cmd

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
        self.install_dir(self.target_dir)
        self._install_targets(x.rstrip(os.path.sep) for x in self.targets)

    def _install_targets(self, targets):
        """Install targets.

        Args:
            targets: files/symlinks/dirs/etc to install
        """
        for x in targets:
            if os.path.isdir(x):
                if self.opts.recursive:
                    self._install_from_dir(x)
            else:
                self._install_files([x], self.target_dir)

    def _install_files(self, files, dest_dir):
        """Install files into a given directory.

        Args:
            files: paths to files to install
            dest_dir: target directory to install files to
        """
        for path in files:
            self.install(path, dest_dir)

    def _install_from_dir(self, source):
        """Install from directory at |source|.

        Args:
            source: Path to the source directory.
        """
        dest_dir = pjoin(self.target_dir, os.path.basename(source))
        self.install_dir(dest_dir)

        def files():
            for dirpath, dirnames, filenames in os.walk(source):
                for dirname in dirnames:
                    source_dir = pjoin(dirpath, dirname)
                    relpath = os.path.relpath(source_dir, self.opts.cwd)
                    if os.path.islink(source_dir):
                        yield relpath
                    else:
                        self.install_dir(pjoin(self.target_dir, relpath))
                yield from (
                    os.path.relpath(pjoin(dirpath, f), self.opts.cwd) for f in filenames)

        self._install_files(files(), dest_dir)

    @staticmethod
    def _set_attributes(opts, path):
        """Sets attributes the file/dir at given |path|.

        Args:
            path: File/directory path.
        """
        if opts.owner != -1 or opts.group != -1:
            os.lchown(path, opts.owner, opts.group)
        if opts.mode is not None:
            os.chmod(path, opts.mode)

    @staticmethod
    def _set_timestamps(source_stat, dest):
        """Apply timestamps from source_stat to dest.

        Args:
            source_stat: stat result for the source file.
            dest: path to the dest file.
        """
        os.utime(dest, ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns))

    def _is_install_allowed(self, source, source_stat, dest):
        """Returns if installing source into dest should work.

        This is to keep compatibility with the `install` command.

        Args:
            source: path to the source file.
            source_stat: stat result for the source file, using stat()
                rather than lstat(), in order to match the `install`
                command
            dest: path to the dest file.
        Raises:
            IpcCommandError on failure.
        Returns:
            True if it should succeed.
        """
        # To match `install` command, use stat() for source, while
        # lstat() for dest.
        try:
            dest_lstat = os.lstat(dest)
        except FileNotFoundError:
            # It is common to install a file into a new path,
            # so if the destination doesn't exist, ignore it.
            return True
        except OSError as e:
            raise IpcCommandError(f'cannot stat {dest!r}: {e.strerror}')

        # Allowing install, if the target is a symlink.
        if stat.S_ISLNK(dest_lstat.st_mode):
            return True

        # Allowing install, if source file and dest file are different.
        # Note that, later, dest will be unlinked.
        if not os.path.samestat(source_stat, dest_lstat):
            return True

        # Allowing install, in hardlink case, if the actual path are
        # different, because source can be preserved even after dest is
        # unlinked.
        if (dest_lstat.st_nlink > 1 and os.path.realpath(source) != os.path.realpath(dest)):
            return True

        raise IpcCommandError(f'{source!r} and {dest!r} are identical')

    def _install(self, source, dest_dir):
        """Install file at |source| into |dest_dir|.

        Args:
            source: Path to the file to be installed.
            dest_dir: Path to the directory which |source| will be
                installed into.
        Raises:
            IpcCommandError on failure.
        Returns:
            True on success, otherwise False.
        """
        dest = pjoin(dest_dir, os.path.basename(source))
        try:
            sstat = os.stat(source)
        except OSError as e:
            raise IpcCommandError(f'cannot stat {source!r}: {e.strerror}')
        self._is_install_allowed(source, sstat, dest)

        # To emulate the `install` command, remove the dest file in advance.
        try:
            os.unlink(dest)
        except FileNotFoundError:
            # Removing a non-existing entry should be handled as a
            # regular case.
            pass
        except OSError as e:
            raise IpcCommandError(f'failed removing file: {dest!r}: {e.strerror}')
        try:
            shutil.copyfile(source, dest)
            self._set_attributes(self.insoptions, dest)
            if self.insoptions.preserve_timestamps:
                self._set_timestamps(sstat, dest)
        except OSError as e:
            raise IpcCommandError(f'failed copying file: {source!r} to {dest_dir!r}: {e.strerror}')

    def _install_cmd(self, source, dest_dir):
        """Install file at |source| into |dest_dir| using `install` command.

        Args:
            source: Path to the file to be installed.
            dest_dir: Path to the directory which |source| will be installed into.
        Raises:
            IpcCommandError on failure.
        """
        command = ['install'] + self.opts.insoptions + [source, dest_dir]
        try:
            subprocess.run(command, check=True, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            raise IpcCommandError(e.stderr.decode())

    def _install_dir(self, dest):
        """Install dir into |dest|.

        Args:
            dest: Path where a directory should be created.
        Raises:
            IpcCommandError on failure.
        """
        try:
            os.makedirs(dest, exist_ok=True)
        except OSError as e:
            raise IpcCommandError(f'failed creating dir: {dest!r}: {e.strerror}')
        self._set_attributes(self.diroptions, dest)

    def _install_dir_cmd(self, dest):
        """Install dir into |dest| using `install` command.

        Args:
            dest: Path where a directory should be created.
        Raises:
            IpcCommandError on failure.
        """
        command = ['install', '-d'] + self.opts.diroptions + [dest]
        try:
            subprocess.run(command, check=True, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            raise IpcCommandError(e.stderr.decode())

    def install_link(self, source, dest):
        """Install symlink at |source| to |dest|.

        Args:
            source: Path to the file to be installed.
            dest_dir: Path to the directory which |source| will be
                installed into.
        Raises:
            IpcCommandError on failure.
        Returns:
            True on success, otherwise False.
        """
        try:
            try:
                os.unlink(dest)
            except IsADirectoryError:
                shutil.rmtree(dest, ignore_errors=True)
            os.symlink(os.readlink(source), dest)
        except OSError as e:
            raise IpcCommandError(f'failed creating symlink: {source!r} -> {dest!r}: {e.strerror}')


class Doins(_InstallWrapper):
    """Python wrapper for doins."""

    def finalize_args(self, args):
        super().finalize_args(args)
        self.allow_symlinks = self.op.pkg.eapi.options.doins_allow_symlinks

    def _install_files(self, files, dest_dir):
        for path in files:
            if os.path.islink(path):
                if self.allow_symlinks:
                    self.install_link(path, pjoin(dest_dir, os.path.basename(path)))
                    continue
            self.install(path, dest_dir)


class Dodoc(_InstallWrapper):
    """Python wrapper for dodoc."""

    def finalize_args(self, args):
        super().finalize_args(args)
        self.allow_recursive = self.op.pkg.eapi.options.dodoc_allow_recursive

    def _install_targets(self, targets):
        for x in targets:
            if os.path.isdir(x):
                if self.opts.recursive and self.allow_recursive:
                    self._install_from_dir(x)
                else:
                    missing_option = ', missing -r option?' if self.allow_recursive else ''
                    raise IpcCommandError(f'{x} is a directory{missing_option}')
            else:
                self._install_files([x], self.target_dir)
