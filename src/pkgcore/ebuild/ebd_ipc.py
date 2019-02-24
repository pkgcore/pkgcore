import argparse
from functools import wraps
import itertools
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys

from snakeoil.cli import arghparse
from snakeoil.compatibility import IGNORED_EXCEPTIONS
from snakeoil.contexts import chdir
from snakeoil.demandload import demandload
from snakeoil.iterables import partition
from snakeoil.osutils import pjoin

from pkgcore.exceptions import PkgcoreException, PkgcoreUserException

demandload(
    'grp',
    'locale',
    'operator:itemgetter',
    'pwd',
    'pkgcore:os_data',
    'pkgcore.ebuild:portageq',
    'pkgcore.ebuild:atom@atom_mod',
)


class IpcError(PkgcoreException):
    """Generic IPC errors."""

    def __init__(self, msg='', code=1, name=None, **kwargs):
        super().__init__(msg, **kwargs)
        self.msg = msg
        self.code = code
        self.name = name
        self.ret = IpcCommand._encode_ret((code, msg))

    def __str__(self):
        if self.name:
            return f'{self.name}: {self.msg}'
        return self.msg


class IpcInternalError(IpcError):
    """IPC errors related to internal bugs."""


class IpcCommandError(IpcError, PkgcoreUserException):
    """IPC errors related to parsing arguments or running the command."""


class UnknownOptions(IpcCommandError):
    """Unknown options passed to IPC command."""

    def __init__(self, options):
        super().__init__(f"unknown options: {', '.join(map(repr, options))}")


class UnknownArguments(IpcCommandError):
    """Unknown arguments passed to IPC command."""

    def __init__(self, args):
        super().__init__(f"unknown arguments: {', '.join(map(repr, args))}")


class IpcArgumentParser(arghparse.OptionalsParser, arghparse.CustomActionsParser,
                        arghparse.CopyableParser):
    """Raise IPC exception for argparse errors.

    Otherwise standard argparse prints the parser usage then outputs the error
    message to stderr.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('add_help', False)
        super().__init__(*args, **kwargs)

    def error(self, msg):
        raise IpcCommandError(msg)


class IpcCommand(object):
    """Commands sent from the bash side of the ebuild daemon to run."""

    # argument parser for internal options
    parser = None
    # argument parser for command options/arguments
    arg_parser = None
    # override IPC name for error messages
    name = None

    def __init__(self, op):
        self.op = op
        self.ED = op.ED
        self.pkg = op.pkg
        self.eapi = op.pkg.eapi
        self.observer = op.observer
        if self.name is None:
            self.name = self.__class__.__name__.lower()

    def __call__(self, ebd):
        self.opts = arghparse.Namespace()
        self.ebd = ebd
        ret = 0

        # read info from bash side
        nonfatal = self.read() == 'true'
        self.cwd = self.read()
        options = shlex.split(self.read())
        args = self.read().strip('\0')
        args = args.split('\0') if args else []

        # parse args and run command
        with chdir(self.cwd):
            try:
                args = self.parse_args(options, args)
                ret = self.run(args)
            except IpcCommandError as e:
                if nonfatal:
                    ret = (e.code, e.msg)
                else:
                    raise IpcCommandError(msg=e.msg, code=e.code, name=self.name)
            except IGNORED_EXCEPTIONS:
                raise
            except Exception as e:
                raise IpcInternalError('internal failure') from e

        # return completion status to the bash side
        self.write(self._encode_ret(ret))

    @staticmethod
    def _encode_ret(ret):
        """Encode exit status and any returned value to be sent back to the bash side."""
        if ret is None:
            return 0
        elif isinstance(ret, tuple):
            code, response = ret
            return f'{code}\x07{response}'
        elif isinstance(ret, (int, str)):
            return f'0\x07{ret}'
        raise TypeError(f'unsupported return status type: {type(ret)}')

    def parse_args(self, options, args):
        """Parse internal args passed from the bash side."""
        if self.parser is not None:
            _, unknown = self.parser.parse_known_args(options, namespace=self.opts)
            if unknown:
                raise UnknownOptions(unknown)

        if self.arg_parser is not None:
            # pull user options off the start of the argument list
            _, args = self.arg_parser.parse_known_optionals(args, namespace=self.opts)
            # parse remaining command arguments
            args, unknown = self.arg_parser.parse_known_args(args, namespace=self.opts)
            if unknown:
                raise UnknownArguments(unknown)
        return args

    def run(self, args):
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
        self.observer.warn(f'{self.name}: {msg}')
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


def existing_path(path):
    """Check if a given path exists (allows broken symlinks)."""
    if not os.path.lexists(path):
        raise argparse.ArgumentTypeError(f'nonexistent path: {path!r}')
    return path


class _InstallWrapper(IpcCommand):
    """Python wrapper for commands using `install`."""

    parser = IpcArgumentParser()
    parser.add_argument('--dest', required=True)
    parser.add_argument('--insoptions', type=command_options)
    parser.add_argument('--diroptions', type=command_options)

    # defaults options for file and dir install actions
    insoptions_default = ''
    diroptions_default = ''

    # supported install command options
    install_parser = IpcArgumentParser()
    install_parser.add_argument('-g', '--group', default=-1, type=_parse_group)
    install_parser.add_argument('-o', '--owner', default=-1, type=_parse_user)
    install_parser.add_argument('-m', '--mode', default=0o755, type=_parse_mode)
    install_parser.add_argument('-p', '--preserve-timestamps', action='store_true')

    arg_parser = IpcArgumentParser()
    arg_parser.add_argument('targets', nargs='+', type=existing_path)

    # boolean for whether symlinks are allowed to be installed
    allow_symlinks = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parser.set_defaults(
            insoptions=self.insoptions_default,
            diroptions=self.diroptions_default)
        # default to python-based install cmds
        self.install = self._install
        self.install_dirs = self._install_dirs

    def parse_args(self, *args, **kwargs):
        args = super().parse_args(*args, **kwargs)
        self.parse_install_options()
        return args

    def parse_install_options(self):
        """Parse install command options."""
        self.insoptions = arghparse.Namespace()
        self.diroptions = arghparse.Namespace()
        if self.opts.insoptions:
            if not self._parse_install_options(self.opts.insoptions, self.insoptions):
                self.install = self._install_cmd
        if self.opts.diroptions:
            if not self._parse_install_options(self.opts.diroptions, self.diroptions):
                self.install_dirs = self._install_dirs_cmd

    def _parse_install_options(self, options, namespace):
        """Internal install command option parser.

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

    def run(self, args):
        try:
            dest_dir = pjoin(self.ED, self.opts.dest.lstrip(os.path.sep))
            os.makedirs(dest_dir, exist_ok=True)
        except OSError as e:
            raise IpcCommandError(
                f'failed creating dir: {dest_dir!r}: {e.strerror}')
        self._install_targets(args.targets)

    def _prefix_targets(files):
        """Decorator to prepend targets being installed with the destination path."""
        def wrapper(func):
            @wraps(func)
            def wrapped(self, targets):
                dest_dir = self.opts.dest.lstrip(os.path.sep)
                if files:
                    targets = ((s, pjoin(self.ED, dest_dir, d)) for s, d in targets)
                else:
                    targets = (pjoin(self.ED, dest_dir, d) for d in targets)
                return func(self, targets)
            return wrapped
        return wrapper

    def _install_targets(self, targets):
        """Install targets.

        Args:
            targets: files/symlinks/dirs/etc to install
        """
        files = ((f, os.path.basename(f)) for f in targets)
        self._install_files(files)

    def _install_files(self, files):
        """Install files into a given directory.

        Args:
            files: iterable of (path, target dir) tuples of files to install
        """
        files, symlinks = partition(files, predicate=lambda x: os.path.islink(x[0]))
        self.install(files)
        # TODO: warn on symlinks when not supported?
        if self.allow_symlinks:
            self.install_symlinks(symlinks)

    def _install_from_dirs(self, dirs):
        """Install all targets under given directories.

        Args:
            dirs: iterable of directories to install from
        """
        def scan_dirs(paths):
            for d in paths:
                dest_dir = os.path.basename(d)
                yield True, dest_dir
                for dirpath, dirnames, filenames in os.walk(d):
                    for dirname in dirnames:
                        source_dir = pjoin(dirpath, dirname)
                        relpath = os.path.relpath(source_dir, self.cwd)
                        if os.path.islink(source_dir):
                            dest = pjoin(dest_dir, os.path.basename(relpath))
                            yield False, (relpath, dest)
                        else:
                            yield True, relpath
                    for f in filenames:
                        source = os.path.relpath(pjoin(dirpath, f), self.cwd)
                        dest = pjoin(dest_dir, os.path.basename(f))
                        yield False, (source, dest)

        # determine all files and dirs under target directories and install them
        files, dirs = partition(scan_dirs(dirs), predicate=itemgetter(0))
        self.install_dirs(x for _, x in dirs)
        self._install_files(x for _, x in files)

    @staticmethod
    def _set_attributes(opts, path):
        """Set file attributes on a given path.

        Args:
            path: file/directory path
        """
        try:
            if opts.owner != -1 or opts.group != -1:
                os.lchown(path, opts.owner, opts.group)
            if opts.mode is not None:
                os.chmod(path, opts.mode)
        except OSError as e:
            raise IpcCommandError(
                f'failed setting file attributes: {path!r}: {e.strerror}')

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

    @_prefix_targets(files=True)
    def _install(self, files):
        """Install files.

        Args:
            files: iterable of (source, dest) tuples of files to install
        Raises:
            IpcCommandError on failure
        """
        for source, dest in files:
            try:
                sstat = os.stat(source)
            except OSError as e:
                raise IpcCommandError(f'cannot stat {source!r}: {e.strerror}')

            self._is_install_allowed(source, sstat, dest)

            # matching `install` command, remove dest before file install
            try:
                os.unlink(dest)
            except FileNotFoundError:
                pass
            except OSError as e:
                raise IpcCommandError(f'failed removing file: {dest!r}: {e.strerror}')

            try:
                shutil.copyfile(source, dest)
                if self.insoptions:
                    self._set_attributes(self.insoptions, dest)
                    if self.insoptions.preserve_timestamps:
                        self._set_timestamps(sstat, dest)
            except OSError as e:
                raise IpcCommandError(
                    f'failed copying file: {source!r} to {dest!r}: {e.strerror}')

    @_prefix_targets(files=True)
    def _install_cmd(self, files):
        """Install files using `install` command.

        Args:
            files: iterable of (source, dest) tuples of files to install
        Raises:
            IpcCommandError on failure
        """
        files = sorted(files, key=itemgetter(1))
        for dest, files_group in itertools.groupby(files, itemgetter(1)):
            sources = list(path for path, _ in files_group)
            command = ['install'] + self.opts.insoptions + sources + [dest]
            try:
                subprocess.run(command, check=True, stderr=subprocess.PIPE)
            except subprocess.CalledProcessError as e:
                raise IpcCommandError(e.stderr.decode(), code=e.returncode)

    @_prefix_targets(files=False)
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
                if self.diroptions:
                    self._set_attributes(self.diroptions, d)
        except OSError as e:
            raise IpcCommandError(f'failed creating dir: {d!r}: {e.strerror}')

    @_prefix_targets(files=False)
    def _install_dirs_cmd(self, dirs):
        """Create directories using `install` command.

        Args:
            dirs: iterable of paths where directories should be created
        Raises:
            IpcCommandError on failure
        """
        command = ['install', '-d'] + self.opts.diroptions + list(dirs)
        try:
            subprocess.run(command, check=True, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            raise IpcCommandError(e.stderr.decode(), code=e.returncode)

    @_prefix_targets(files=True)
    def install_symlinks(self, symlinks):
        """Install iterable of symlinks.

        Args:
            symlinks: iterable of (path, target dir) tuples of symlinks to install
        Raises:
            IpcCommandError on failure
        """
        try:
            for symlink, dest in symlinks:
                os.symlink(os.readlink(symlink), dest)
        except OSError as e:
            raise IpcCommandError(
                f'failed creating symlink: {symlink!r} -> {dest!r}: {e.strerror}')


class Doins(_InstallWrapper):
    """Python wrapper for doins."""

    arg_parser = _InstallWrapper.arg_parser.copy()
    arg_parser.add_argument('-r', dest='recursive', action='store_true')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.allow_symlinks = self.eapi.options.doins_allow_symlinks

    def _install_targets(self, targets):
        files, dirs = partition(targets, predicate=os.path.isdir)
        if self.opts.recursive:
            self._install_from_dirs(dirs)
        files = ((f, os.path.basename(f)) for f in files)
        self._install_files(files)


class Dodoc(_InstallWrapper):
    """Python wrapper for dodoc."""

    insoptions_default = '-m0644'

    arg_parser = _InstallWrapper.arg_parser.copy()
    arg_parser.add_argument('-r', dest='recursive', action='store_true')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.allow_recursive = self.eapi.options.dodoc_allow_recursive

    def _install_targets(self, targets):
        files, dirs = partition(targets, predicate=os.path.isdir)
        # TODO: add peekable class for iterables to avoid list conversion
        dirs = list(dirs)
        if dirs:
            if self.opts.recursive and self.allow_recursive:
                self._install_from_dirs(dirs)
            else:
                missing_option = ', missing -r option?' if self.allow_recursive else ''
                raise IpcCommandError(f'{dirs[0]!r} is a directory{missing_option}')
        # TODO: skip/warn installing empty files
        files = ((f, os.path.basename(f)) for f in files)
        self._install_files(files)


class Doinfo(_InstallWrapper):
    """Python wrapper for doinfo."""

    insoptions_default = '-m0644'


class Dodir(_InstallWrapper):
    """Python wrapper for dodir."""

    diroptions_default = '-m0755'

    arg_parser = IpcArgumentParser()
    arg_parser.add_argument('targets', nargs='+')

    def run(self, args):
        self.install_dirs(args.targets)


class Doexe(_InstallWrapper):
    """Python wrapper for doexe."""


class Dobin(_InstallWrapper):
    """Python wrapper for dobin."""

    def parse_install_options(self, *args, **kwargs):
        # TODO: fix this to be prefix aware at some point
        self.opts.insoptions = [
            '-m0755', f'-g{os_data.root_gid}', f'-o{os_data.root_uid}']
        return super().parse_install_options(*args, **kwargs)


class Dosbin(Dobin):
    """Python wrapper for dosbin."""


class Dolib(_InstallWrapper):
    """Python wrapper for dolib."""

    allow_symlinks = True


class Dolib_so(Dolib):
    """Python wrapper for dolib.so."""

    name = 'dolib.so'


class Dolib_a(Dolib):
    """Python wrapper for dolib.a."""

    name = 'dolib.a'


class Doman(_InstallWrapper):
    """Python wrapper for doman."""

    insoptions_default = '-m0644'

    arg_parser = _InstallWrapper.arg_parser.copy()
    arg_parser.add_argument('-i18n', action='store_true', default='')

    detect_lang_re = re.compile(r'^(\w+)\.([a-z]{2}([A-Z]{2})?)\.(\w+)$')
    valid_mandir_re = re.compile(r'man[0-9n](f|p|pm)?$')

    allow_symlinks = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.language_detect = self.eapi.options.doman_language_detect
        self.language_override = self.eapi.options.doman_language_override

    def _filter_targets(self, files):
        dirs = set()
        for f in files:
            basename = os.path.basename(f)
            suffix = os.path.splitext(basename)[1]

            if self.eapi.archive_suffixes_re.match(suffix):
                # TODO: uncompress/warn?
                suffix = os.path.splitext(basename.rsplit('.', 1)[0])[1]

            name = basename
            mandir = f'man{suffix[1:]}'

            if self.language_override and self.opts.i18n:
                mandir = pjoin(self.opts.i18n, mandir)
            elif self.language_detect:
                match = self.detect_lang_re.match(basename)
                if match:
                    name = f'{match.group(0)}.{match.group(3)}'
                    mandir = pjoin(match.group(1), mandir)

            if self.valid_mandir_re.match(mandir):
                if mandir not in dirs:
                    yield True, mandir
                    dirs.add(mandir)
                yield False, (f, pjoin(mandir, name))
            else:
                raise IpcCommandError(f'invalid man page: {f}')

    def _install_targets(self, targets):
        # TODO: skip/warn installing empty files
        targets = self._filter_targets(targets)
        files, dirs = partition(targets, predicate=itemgetter(0))
        self.install_dirs(x for _, x in dirs)
        self._install_files(x for _, x in files)


class Domo(_InstallWrapper):
    """Python wrapper for domo."""

    insoptions_default = '-m0644'

    def _filter_targets(self, files):
        dirs = set()
        for f in files:
            d = pjoin(os.path.splitext(os.path.basename(f))[0], 'LC_MESSAGES')
            if d not in dirs:
                yield True, d
                dirs.add(d)
            yield False, (f, pjoin(d, f'{self.pkg.PN}.mo'))

    def _install_targets(self, targets):
        # TODO: skip/warn installing empty files
        targets = self._filter_targets(targets)
        files, dirs = partition(targets, predicate=itemgetter(0))
        self.install_dirs(x for _, x in dirs)
        self._install_files(x for _, x in files)


class Dohtml(_InstallWrapper):
    """Python wrapper for dohtml."""

    insoptions_default = '-m0644'

    arg_parser = _InstallWrapper.arg_parser.copy()
    arg_parser.add_argument('-r', dest='recursive', action='store_true')
    arg_parser.add_argument('-V', dest='verbose', action='store_true')
    arg_parser.add_argument('-A', dest='extra_allowed_file_exts', action='csv', default=[])
    arg_parser.add_argument('-a', dest='allowed_file_exts', action='csv', default=[])
    arg_parser.add_argument('-f', dest='allowed_files', action='csv', default=[])
    arg_parser.add_argument('-x', dest='excluded_dirs', action='csv', default=[])
    arg_parser.add_argument('-p', dest='doc_prefix', default='')

    # default allowed file extensions
    default_allowed_file_exts = ('css', 'gif', 'htm', 'html', 'jpeg', 'jpg', 'js', 'png')

    def parse_args(self, *args, **kwargs):
        args = super().parse_args(*args, **kwargs)
        self.opts.dest = pjoin(self.opts.dest, self.opts.doc_prefix.lstrip(os.path.sep))

        if not self.opts.allowed_file_exts:
            self.opts.allowed_file_exts = list(self.default_allowed_file_exts)
        self.opts.allowed_file_exts.extend(self.opts.extra_allowed_file_exts)

        self.opts.allowed_file_exts = set(self.opts.allowed_file_exts)
        self.opts.excluded_dirs = set(self.opts.excluded_dirs)
        self.opts.allowed_files = set(self.opts.allowed_files)

        if self.opts.verbose:
            self.observer.write(str(self) + '\n')
            self.observer.flush()

        return args

    def __str__(self):
        msg = ['dohtml:', f'  Installing to: {self.opts.dest}']
        if self.opts.allowed_file_exts:
            msg.append(
                f"  Allowed extensions: {', '.join(sorted(self.opts.allowed_file_exts))}")
        if self.opts.excluded_dirs:
            msg.append(
                f"  Allowed extensions: {', '.join(sorted(self.opts.allowed_file_exts))}")
        if self.opts.allowed_files:
            msg.append(
                f"  Allowed files: {', '.join(sorted(self.opts.allowed_files))}")
        if self.opts.doc_prefix:
            msg.append(f"  Document prefix: {self.opts.doc_prefix!r}")
        return '\n'.join(msg)

    def _install_targets(self, targets):
        files, dirs = partition(targets, predicate=os.path.isdir)
        # TODO: add peekable class for iterables to avoid list conversion
        dirs = list(dirs)
        if dirs:
            if self.opts.recursive:
                dirs = (d for d in dirs if d not in self.opts.excluded_dirs)
                self._install_from_dirs(dirs)
            else:
                raise IpcCommandError(f'{dirs[0]!r} is a directory, missing -r option?')
        files = ((f, os.path.basename(f)) for f in files)
        self._install_files(files)

    def _allowed_file(self, item):
        """Determine if a file is allowed to be installed."""
        path, dest = item
        basename = os.path.basename(path)
        ext = os.path.splitext(basename)[1][1:]
        return (ext in self.opts.allowed_file_exts or basename in self.opts.allowed_files)

    def _install_files(self, files):
        self.install(f for f in files if self._allowed_file(f))


class _AlterFiles(IpcCommand):

    arg_parser = IpcArgumentParser()
    arg_parser.add_argument('-x', dest='excludes', action='store_true')
    arg_parser.add_argument('targets', nargs='+')

    default_includes = ()
    default_excludes = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.includes = set(self.default_includes)
        self.excludes = set(self.default_excludes)

    def run(self, args):
        if self.opts.excludes:
            self.excludes.update(args.targets)
        else:
            self.includes.update(args.targets)


class Docompress(_AlterFiles):
    """Python wrapper for docompress."""

    default_includes = ('/usr/share/doc', '/usr/share/info', '/usr/share/man')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.excludes = {f'/usr/share/doc/{self.pkg.PF}/html'}


class Dostrip(_AlterFiles):
    """Python wrapper for dostrip."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'strip' not in self.pkg.restrict:
            self.includes = {'/'}


class _QueryCmd(IpcCommand):

    arg_parser = IpcArgumentParser()
    arg_parser.add_argument('atom', type=atom_mod.atom)

    # >= EAPI 5
    host_root_parser = IpcArgumentParser()
    host_root_parser.add_argument('--host-root', action='store_true')

    # >= EAPI 7
    query_deps_parser = IpcArgumentParser()
    dep_opts = query_deps_parser.add_mutually_exclusive_group()
    dep_opts.add_argument('-b', dest='bdepend', action='store_true')
    dep_opts.add_argument('-d', dest='depend', action='store_true')
    dep_opts.add_argument('-r', dest='rdepend', action='store_true')

    def parse_args(self, options, args):
        # parse EAPI specific optionals then remaining args
        if self.eapi.options.query_host_root:
            _, args = self.host_root_parser.parse_known_optionals(args, namespace=self.opts)
        elif self.eapi.options.query_deps:
            _, args = self.query_deps_parser.parse_known_optionals(args, namespace=self.opts)
        args = super().parse_args(options, args)

        root = None
        self.opts.domain = self.op.domain

        if self.eapi.options.query_host_root and self.opts.host_root:
            root = '/'
        elif self.eapi.options.query_deps:
            if self.opts.bdepend:
                if self.op.prefix_mode:
                    # not using BROOT as that's only defined in src_* phases
                    root = pjoin('/', self.op.env['EPREFIX'])
                else:
                    root = '/'
            elif self.opts.depend:
                if self.op.prefix_mode:
                    root = self.op.env['ESYSROOT']
                else:
                    root = self.op.env['SYSROOT']
            else:
                if self.op.prefix_mode:
                    root = self.op.env['EROOT']
                else:
                    root = self.op.env['ROOT']

        # TODO: find domain from given path, pointless until full prefix support works
        if root is not None and root != self.opts.domain.root:
            raise IpcCommandError('prefix support not implemented yet')

        return args


class Has_Version(_QueryCmd):
    """Python wrapper for has_version."""

    def run(self, args):
        if args.atom in self.opts.domain.all_installed_repos:
            return 0
        return 1


class Best_Version(_QueryCmd):
    """Python wrapper for best_version."""

    def run(self, args):
        return portageq._best_version(self.opts.domain, args.atom)


class Eapply(IpcCommand):

    arg_parser = IpcArgumentParser()
    arg_parser.add_argument('targets', nargs='+', type=existing_path)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.patch_cmd = ['patch', '-p1', '-f', '-s', '-g0', '--no-backup-if-mismatch']

    def _parse_patch_opts(self, args):
        patch_opts = []
        files = []
        for i, arg in enumerate(args):
            if arg == '--':
                if files:
                    raise IpcCommandError('options must be specified before file arguments')
                files = args[i + l:]
                break
            elif arg.startswith('-'):
                if files:
                    raise IpcCommandError('options must be specified before file arguments')
                patch_opts.append(arg)
            else:
                files.append(arg)
        return files, patch_opts

    def _find_patches(self, args):
        for path in args:
            if os.path.isdir(path):
                for root, _dirs, files in os.walk(path):
                    patches = [
                        pjoin(root, f) for f in sorted(files, key=locale.strxfrm)
                        if f.endswith(('.diff', '.patch'))]
                    if not patches:
                        raise IpcCommandError(f'no patches in directory: {path!r}')
                    yield path, patches
            else:
                yield None, [path]

    def parse_args(self, options, args):
        args, patch_opts = self._parse_patch_opts(args)
        self.opts.patch_opts = patch_opts
        args = super().parse_args(options, args)
        return self._find_patches(args.targets)

    def run(self, args, user=False):
        if user:
            patch_type = 'user patches'
            output = self.observer.warn
        else:
            patch_type = 'patches'
            output = self.observer.info

        try:
            for path, patches in args:
                prefix = ''
                if path is not None:
                    output(f'Applying {patch_type} from {path!r}:')
                    prefix = '  '
                for patch in patches:
                    output(f'{prefix}{os.path.basename(patch)}')
                    self.observer.flush()
                    with open(patch) as f:
                        subprocess.run(
                            self.patch_cmd + self.opts.patch_opts,
                            check=True, stdin=f, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            filename = os.path.basename(patch)
            msg = f'applying {filename!r} failed: {e.stderr.decode()}'
            raise IpcCommandError(msg, code=e.returncode)
        except OSError as e:
            raise IpcCommandError(
                f'failed reading patch file: {patch!r}: {e.strerror}')


class Eapply_User(IpcCommand):

    # stub parser so any arguments are flagged as errors
    arg_parser = IpcArgumentParser()

    def run(self, args):
        if self.pkg.user_patches:
            self.op._ipc_helpers['eapply'].run(self.pkg.user_patches, user=True)

        # create marker to skip additionals calls
        patches = itertools.chain.from_iterable(
            files for _, files in self.pkg.user_patches)
        with open(pjoin(self.op.env['T'], '.user_patches_applied'), 'w') as f:
            f.write('\n'.join(patches))
