"""pmerge formatting module"""

__all__ = (
    "Formatter", "use_expand_filter",
    "BasicFormatter", "PkgcoreFormatter", "CountingFormatter",
    "PortageFormatter", "PortageVerboseFormatter", "PaludisFormatter",
)

import operator
import os

from snakeoil.cli.input import userquery
from snakeoil.mappings import defaultdictkey
from snakeoil.osutils import pjoin, sizeof_fmt
from snakeoil.sequences import iflatten_instance
from snakeoil.strings import pluralism

from ..config.hint import ConfigHint
from ..log import logger


class use_expand_filter:

    def __init__(self, use_expand, use_expand_hidden):
        """
        :type use_expand: iterable of strings
        :param use_expand: names of use-expanded variables.
        :type use_expand_hidden: set of strings
        :param use_expand_hidden: names of use-expanded vars that should not
            be added to the dict.
        """
        self.expand_filters = {x.lower(): (x not in use_expand_hidden, x)
                               for x in use_expand}
        self.use_expand = use_expand
        self.use_expand_hidden = use_expand_hidden
        self.known_flags = {}

    def __call__(self, use):
        """Split USE flags up into "normal" flags and use-expanded ones.
        :type use: iterable of strings
        :param use: flags that are set.
        :rtype: sequence of strings, dict mapping a string to a list of strings
        :return: set of normal flags and a mapping from use_expand name to
            value (with the use-expanded bit stripped off, so
            C{"video_cards_alsa"} becomes C{"{'video_cards': ['alsa']}"}).
        """
        # XXX: note this is fairly slow- actually takes up more time then
        # chunks of the resolver
        ue_dict = {}
        usel = []
        ef = self.expand_filters
        kf = self.known_flags

        for flag in use:
            data = kf.get(flag)
            if data is None:
                split_flag = flag.rsplit("_", 1)
                while len(split_flag) == 2:
                    if split_flag[0] not in ef:
                        split_flag = split_flag[0].rsplit("_", 1)
                        continue
                    expand_state = ef[split_flag[0]]
                    if expand_state[0]:
                        # not hidden
                        kf[flag] = data = (expand_state[1], flag[len(split_flag[0]) + 1:])
                    else:
                        kf[flag] = data = False
                    break
                else:
                    kf[flag] = data = True
            if data is True:
                # straight use flag.
                usel.append(flag)
            elif data:
                # non hidden flag.
                if not data[0] in ue_dict:
                    ue_dict[data[0]] = set([data[1]])
                else:
                    ue_dict[data[0]].add(data[1])

        return frozenset(usel), ue_dict


class Formatter:
    """Base Formatter class: All formatters should be subclasses of this."""

    pkgcore_config_type = ConfigHint(typename='pmerge_formatter', raw_class=True)

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def format(self, op):
        """Formats an op. Subclasses must define this method"""
        raise NotImplementedError(self.format)

    def ask(self, question, responses=None, default_answer=None, limit=3):
        return userquery(
            question, self.out, self.err, responses, default_answer, limit)

    def end(self):
        """Called at the end, normally for summary information"""


class BasicFormatter(Formatter):
    """A basic formatter, intended for scripts"""

    def format(self, op):
        self.out.write(op.pkg.key)


class VerboseFormatter(Formatter):
    """Formatter with output forced into verbose mode."""

    def __init__(self, **kwargs):
        kwargs['verbosity'] = 1
        super().__init__(**kwargs)


class PkgcoreFormatter(Formatter):
    """The original pkgcore output"""

    def format(self, op):
        repo = getattr(op.pkg.repo, 'repo_id', None)
        if not repo:
            p = str(op.pkg.cpvstr)
        else:
            p = f"{op.pkg.cpvstr}::{repo}"
        if op.desc == "replace":
            self.out.write(f"replace {op.old_pkg.cpvstr}, {p}")
        else:
            self.out.write(f"{op.desc.ljust(7)} {p}")


class CountingFormatter(Formatter):
    """Subclass for formatters that count packages"""

    def __init__(self, **kwargs):
        kwargs.setdefault("verbosity", 0)
        super().__init__(**kwargs)
        self.package_data = defaultdictkey(lambda x: 0)

        # total download size for all pkgs to be merged
        self.download_size = 0

    def visit_op(self, op_type):
        """Track the number of package operations of each type."""
        self.package_data[op_type] += 1

    def end(self):
        """Output total package, operation, and download size counts."""
        self.out.write()
        if self.verbosity > 0:
            total = sum(self.package_data.values())
            self.out.write(
                f"Total: {total} package{pluralism(total)}", autoline=False)

            d = dict(self.package_data.items())
            op_types = (
                ('add', 'new'),
                ('upgrade', 'upgrade'),
                ('downgrade', 'downgrade'),
                ('slotted_add', 'in new slot'),
                ('replace', 'reinstall'),
            )
            op_list = []
            for op_type, op_str in op_types:
                num_ops = d.pop(op_type, 0)
                if num_ops:
                    if op_str == 'new':
                        op_list.append(f"{num_ops} {op_str}")
                    else:
                        op_list.append(f"{num_ops} {op_str}{pluralism(num_ops)}")
            if d:
                op_list.append(f"{len(d)} other op{pluralism(d)}")
            if op_list:
                self.out.write(f" ({', '.join(op_list)})", autoline=False)
            if self.download_size:
                self.out.write(
                    ', Size of downloads: ', sizeof_fmt(self.download_size), autoline=False)
            self.out.write()


class PortageFormatter(CountingFormatter):
    """Formatter designed to resemble portage output."""

    def __init__(self, **kwargs):
        kwargs.setdefault("use_expand", set())
        kwargs.setdefault("use_expand_hidden", set())
        super().__init__(**kwargs)
        self.use_splitter = use_expand_filter(
            self.use_expand, self.use_expand_hidden)
        # Map repo location to an index.
        self.repos = {}
        # set of files to be downloaded
        self.downloads = set()

    def format(self, op):
        # <type>       - ebuild, block or nomerge (for --tree)
        #       N      - new package
        #        R     - rebuild package
        #         F    - fetch restricted
        #         f    - fetch restricted already downloaded
        #          D   - downgrade
        #           U  - updating to another version
        #            # - masked
        #            * - missing keyword
        #            ~ - unstable keyword
        # Caveats:
        # - U and D are both displayed to show a downgrade - this is kept
        # in order to be consistent with existing portage behaviour

        out = self.out
        origautoline = out.autoline
        out.autoline = False

        self.pkg_disabled_use = self.pkg_forced_use = set()
        if hasattr(self, 'pkg_get_use'):
            self.pkg_forced_use, _, self.pkg_disabled_use = self.pkg_get_use(op.pkg)

        # This is for the summary at the end
        if self.quiet_repo_display:
            self.repos.setdefault(op.pkg.repo, len(self.repos)+1)

        pkg_is_bold = any(x.match(op.pkg) for x in getattr(self, 'world_list', ()))

        # We don't do blockers or --tree stuff yet
        data = ['[']
        pkg_coloring = []
        if pkg_is_bold:
            pkg_coloring.append(out.bold)
        if op.desc == 'remove':
            pkg_coloring.insert(0, out.fg('red'))
            data += pkg_coloring + ['uninstall']
        elif getattr(op.pkg, 'built', False):
            pkg_coloring.insert(0, out.fg('magenta'))
            data += pkg_coloring + ['binary']
        else:
            pkg_coloring.insert(0, out.fg('green'))
            data += pkg_coloring + ['ebuild']

        data += [out.reset, ' ']
        out.write(*data)

        # Order is important here - look at the above diagram
        op_type = op.desc
        op_chars = [[' '] for x in range(7)]
        if 'fetch' in op.pkg.restrict:
            if all(os.path.isfile(pjoin(self.distdir, f))
                   for f in op.pkg.distfiles):
                fetched = [out.fg('green'), out.bold, 'f', out.reset]
            else:
                fetched = [out.fg('red'), out.bold, 'F', out.reset]
            op_chars[3] = fetched

        if op.desc == "add":
            op_chars[1] = [out.fg('green'), out.bold, 'N', out.reset]
            if op.pkg.slot != '0' and self.installed_repos.match(op.pkg.unversioned_atom):
                op_chars[2] = [out.fg('green'), out.bold, 'S', out.reset]
                op_type = 'slotted_add'
        elif op.desc == "replace":
            if op.pkg == op.old_pkg:
                op_chars[2] = [out.fg('yellow'), out.bold, 'R', out.reset]
            else:
                op_chars[4] = [out.fg('cyan'), out.bold, 'U', out.reset]
                if op.pkg > op.old_pkg:
                    op_type = 'upgrade'
                else:
                    op_chars[5] = [out.fg('blue'), out.bold, 'D', out.reset]
                    op_type = 'downgrade'
        elif op.desc == 'remove':
            pass
        else:
            logger.warning("unformattable op type: desc(%r), %r", op.desc, op)

        if self.verbosity > 0:
            if (self.unstable_arch in op.pkg.keywords and
                    self.unstable_arch not in op.pkg.repo.domain_settings['ACCEPT_KEYWORDS']):
                op_chars[6] = [out.fg('yellow'), out.bold, '~', out.reset]
            elif not op.pkg.keywords:
                op_chars[6] = [out.fg('red'), out.bold, '*', out.reset]
            else:
                if op.pkg.repo.masked.match(op.pkg.versioned_atom):
                    op_chars[6] = [out.fg('red'), out.bold, '#', out.reset]

        out.write(*(iflatten_instance(op_chars)))
        out.write('] ')

        self.visit_op(op_type)

        pkg = [op.pkg.cpvstr]
        if self.verbosity > 0:
            if op.pkg.subslot != op.pkg.slot:
                pkg.append(f":{op.pkg.slot}/{op.pkg.subslot}")
            elif op.pkg.slot != '0':
                pkg.append(f":{op.pkg.slot}")
            if not self.quiet_repo_display and op.pkg.source_repository:
                pkg.append(f"::{op.pkg.source_repository}")
        out.write(*(pkg_coloring + pkg + [out.reset]))

        installed = []
        if op.desc == 'replace':
            old_pkg = [op.old_pkg.fullver]
            if self.verbosity > 0:
                if op.old_pkg.subslot != op.old_pkg.slot:
                    old_pkg.append(f":{op.old_pkg.slot}/{op.old_pkg.subslot}")
                elif op.old_pkg.slot != '0':
                    old_pkg.append(f":{op.old_pkg.slot}")
                if not self.quiet_repo_display and op.old_pkg.source_repository:
                    old_pkg.append(f"::{op.old_pkg.source_repository}")
            if op_type != 'replace' or op.pkg.source_repository != op.old_pkg.source_repository:
                installed = ''.join(old_pkg)
        elif op_type == 'slotted_add':
            if self.verbosity > 0:
                pkgs = sorted(
                    f"{x.fullver}:{x.slot}" for x in
                    self.installed_repos.match(op.pkg.unversioned_atom))
            else:
                pkgs = sorted(
                    x.fullver for x in
                    self.installed_repos.match(op.pkg.unversioned_atom))
            installed = ', '.join(pkgs)

        # output currently installed versions
        if installed:
            out.write(' ', out.fg('blue'), out.bold, f'[{installed}]', out.reset)

        # Build a list of (useflags, use_expand_dicts) tuples.
        # HACK: if we are in "replace" mode we build a list of length
        # 4, else this is a list of length 2. We then pass this to
        # format_use which can take either 2 or 4 arguments.
        uses = ((), ())
        if op.desc == 'replace':
            uses = (
                op.pkg.iuse_stripped, op.pkg.use,
                op.old_pkg.iuse_stripped, op.old_pkg.use)
        elif op.desc == 'add':
            uses = (op.pkg.iuse_stripped, op.pkg.use)
        stuff = list(map(self.use_splitter, uses))

        # Convert the list of tuples to a list of lists and a list of
        # dicts (both length 2 or 4).
        uselists, usedicts = list(zip(*stuff))

        # output USE flags
        self.format_use('use', *uselists)

        # output USE_EXPAND flags
        for expand in sorted(self.use_expand - self.use_expand_hidden):
            flaglists = [d.get(expand, ()) for d in usedicts]
            self.format_use(expand, *flaglists)

        # output download size
        if self.verbosity > 0:
            if not op.pkg.built:
                downloads = set(
                    f for f in op.pkg.distfiles
                    if not os.path.isfile(pjoin(self.distdir, f)))
                if downloads.difference(self.downloads):
                    self.downloads.update(downloads)
                    size = sum(
                        v['size'] for dist, v in
                        op.pkg.manifest.distfiles.items() if dist in downloads)
                    if size:
                        self.download_size += size
                        out.write(' ', sizeof_fmt(size))

            if self.quiet_repo_display:
                out.write(out.fg('cyan'), f" [{self.repos[op.pkg.repo]}]")

        out.write('\n')
        out.autoline = origautoline

    def format_use(self, attr, pkg_iuse, pkg_use, old_pkg_iuse=None, old_pkg_use=None):
        """Write the current selection from a set of flags to a formatter.

        :type attr: string
        :param attr: name of the setting
        :type pkg_iuse: set of strings
        :param pkg_iuse: all available use flags for the package
        :type pkg_use: set of strings
        :param pkg_use: enabled use flags for the package
        :type old_pkg_iuse: set of strings
        :param old_pkg_iuse: all available use flags in the previous version
        :type old_pkg_use: set of strings
        :param old_pkg_use: enabled use flags in the previous version
        """
        out = self.out
        red = out.fg('red')
        green = out.fg('green')
        blue = out.fg('blue')
        yellow = out.fg('yellow')
        bold = out.bold
        reset = out.reset

        flags = []
        enabled = set(pkg_iuse) & set(pkg_use)
        disabled = set(pkg_iuse) - set(pkg_use)

        # updating or rebuilding pkg
        if old_pkg_iuse is not None and old_pkg_use is not None:

            old_enabled = set(old_pkg_iuse) & set(old_pkg_use)
            old_disabled = set(old_pkg_iuse) - set(old_pkg_use)
            removed = set(old_pkg_iuse) - set(pkg_iuse)

            for flag in sorted(enabled):
                expanded_flag = '_'.join((attr.lower(), flag)) if attr != 'use' else flag
                if flag in old_enabled:
                    # unchanged
                    if self.verbosity > 0:
                        if expanded_flag in self.pkg_forced_use:
                            flags.extend(('(', red, bold, flag, reset, ')', ' '))
                        else:
                            flags.extend((red, bold, flag, reset, ' '))
                elif flag in old_disabled:
                    # toggled
                    if expanded_flag in self.pkg_forced_use:
                        flags.extend(('(', green, bold, flag, reset, '*)', ' '))
                    else:
                        flags.extend((green, bold, flag, reset, '*', ' '))
                else:
                    # new
                    if expanded_flag in self.pkg_forced_use:
                        flags.extend(('(', yellow, bold, flag, reset, '%*)', ' '))
                    else:
                        flags.extend((yellow, bold, flag, reset, '%*', ' '))

            for flag in sorted(disabled):
                expanded_flag = '_'.join((attr.lower(), flag)) if attr != 'use' else flag
                if flag in old_disabled:
                    # unchanged
                    if self.verbosity > 0:
                        if expanded_flag in self.pkg_disabled_use:
                            flags.extend(('(', blue, bold, '-', flag, reset, ')', ' '))
                        else:
                            flags.extend((blue, bold, '-', flag, reset, ' '))
                elif flag in old_enabled:
                    # toggled
                    if expanded_flag in self.pkg_disabled_use:
                        flags.extend(('(', green, bold, '-', flag, reset, '*)', ' '))
                    else:
                        flags.extend((green, bold, '-', flag, reset, '*', ' '))
                else:
                    # new
                    if expanded_flag in self.pkg_disabled_use:
                        flags.extend(('(', yellow, bold, '-', flag, reset, '%)', ' '))
                    else:
                        flags.extend((yellow, bold, '-', flag, reset, '%', ' '))

            if self.verbosity > 0:
                for flag in sorted(removed):
                    if flag in old_enabled:
                        flags.extend(('(', yellow, bold, '-', flag, reset, '%*)', ' '))
                    else:
                        flags.extend(('(', yellow, bold, '-', flag, reset, '%)', ' '))

        # new pkg install
        else:
            for flag in sorted(enabled):
                expanded_flag = '_'.join((attr.lower(), flag)) if attr != 'use' else flag
                if expanded_flag in self.pkg_forced_use:
                    flags.extend(('(', red, bold, flag, reset, ')', ' '))
                else:
                    flags.extend((red, bold, flag, reset, ' '))
            for flag in sorted(disabled):
                expanded_flag = '_'.join((attr.lower(), flag)) if attr != 'use' else flag
                if expanded_flag in self.pkg_disabled_use:
                    flags.extend(('(', blue, bold, '-', flag, reset, ')', ' '))
                else:
                    flags.extend((blue, bold, '-', flag, reset, ' '))

        # Only write this if we have something to write
        if flags:
            out.write(' ', attr.upper(), '="')
            # Omit the final space.
            out.write(*flags[:-1])
            out.write('"')

    def end(self):
        """Output package repository list."""
        out = self.out
        if self.verbosity > 0:
            super().end()
            out.write()
            if self.quiet_repo_display:
                repos = list(self.repos.items())
                repos.sort(key=operator.itemgetter(1))
                for k, v in repos:
                    reponame = getattr(k, 'repo_id', 'unknown repo id')
                    location = getattr(k, 'location', 'unspecified location')
                    if reponame != location:
                        self.out.write(
                            ' ', self.out.fg('cyan'), f"[{v}]",
                            self.out.reset, f" {reponame} ({location})")
                    else:
                        self.out.write(
                            ' ', self.out.fg('cyan'), f"[{v}]",
                            self.out.reset, f" {location}")


class PortageVerboseFormatter(VerboseFormatter, PortageFormatter):
    """Formatter designed to resemble portage output in verbose mode."""


class PaludisFormatter(CountingFormatter):
    """Formatter designed to resemble paludis output."""

    def format(self, op):
        out = self.out
        origautoline = out.autoline
        out.autoline = False

        out.write('* ')
        out.write(out.fg('blue'), op.pkg.key)
        out.write(f"-{op.pkg.fullver}")
        out.write(f"::{op.pkg.repo.repo_id} ")
        out.write(out.fg('blue'), f"{{:{op.pkg.slot}}} ")
        op_type = op.desc
        if op.desc == 'add':
            suffix = 'N'
            if op.pkg.slot != '0':
                op_type = 'slotted_add'
                suffix = 'S'
            out.write(out.fg('yellow'), f"[{suffix}]")
        elif op.desc == 'replace':
            if op.pkg != op.old_pkg:
                if op.pkg > op.old_pkg:
                    op_type = 'upgrade'
                else:
                    op_type = 'downgrade'
                out.write(
                    out.fg('yellow'),
                    f"[{op_type[0].upper()} {op.old_pkg.fullver}]")
            else:
                out.write(out.fg('yellow'), "[R]")
        else:
            # shouldn't reach here
            logger.warning("unknown op type encountered: desc(%r), %r", op.desc, op)
        self.visit_op(op_type)

        red = out.fg('red')
        green = out.fg('green')
        flags = []
        use = set(op.pkg.use)
        for flag in sorted(op.pkg.iuse_stripped):
            if flag in use:
                flags.extend((green, flag, ' '))
            else:
                flags.extend((red, '-', flag, ' '))
        if flags:
            out.write(' ')
            # Throw away the final space.
            out.write(*flags[:-1])
        out.write('\n')
        out.autoline = origautoline
