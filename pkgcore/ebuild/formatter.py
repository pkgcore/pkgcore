# Copyright: 2007-2011 Brian Harring <ferringb@gmail.com>
# Copyright: 2007 Charlie Shepherd <masterdriverz@gmail.com>
# License: GPL2/BSD2

"""pmerge formatting module"""

__all__ = ("NoChoice", "userquery", "Formatter", "use_expand_filter",
    "BasicFormatter", "PkgcoreFormatter", "CountingFormatter", "PortageFormatter",
    "PaludisFormatter", "basic_factory", "pkgcore_factory", "portage_factory",
    "paludis_factory", "portage_verbose_factory")

import operator

from pkgcore.config import configurable
from snakeoil.demandload import demandload
from snakeoil.compatibility import raise_from
from snakeoil.lists import iflatten_instance
demandload(globals(),
    'errno',
    'os',
    'pkgcore.log:logger',
    'snakeoil.mappings:defaultdictkey',
    'snakeoil.osutils:pjoin',
)

class NoChoice(KeyboardInterrupt):
    """Raised by :obj:`userquery` if no choice was made.

    HACK: this subclasses KeyboardInterrupt, so if you ignore this it
    should do something reasonable.
    """

def userquery(prompt, out, err, responses=None, default_answer=None, limit=3):
    """Ask the user to choose from a set of options.

    Displays a prompt and a set of responses, then waits for a
    response which is checked against the responses. If there is an
    unambiguous match the value is returned.

    If the user does not input a valid response after a number of
    tries :obj:`NoChoice` is raised. You can catch this if you want to do
    something special. Because it subclasses C{KeyboardInterrupt}
    the default behaviour is to abort as if the user hit ctrl+c.

    :type prompt: C{basestring} or a tuple of things to pass to a formatter.
        XXX this is a crummy api but I cannot think of a better one supporting
        the very common case of wanting just a string as prompt.
    :type out: formatter.
    :type err: formatter.
    :type responses: mapping with C{basestring} keys and tuple values.
    :param responses: mapping of user input to function result.
        The first item in the value tuple is returned, the rest is passed to
        out.  Defaults to::
        {'yes': (True, out.fg('green'), 'Yes'),
        'no': (False, out.fg('red'), 'No')}
    :param default_answer: returned if there is no input
        (user just hits enter). Defaults to True if responses is unset,
        unused otherwise.
    :param limit: number of allowed tries.
    """
    if responses is None:
        responses = {
            'yes': (True, out.fg('green'), 'Yes'),
            'no': (False, out.fg('red'), 'No'),
            }
        if default_answer is None:
            default_answer = True
    if default_answer is not None:
        for val in responses.itervalues():
            if val[0] == default_answer:
                default_answer_name = val[1:]
    for i in xrange(limit):
        # XXX see docstring about crummyness
        if isinstance(prompt, tuple):
            out.write(autoline=False, *prompt)
        else:
            out.write(prompt, autoline=False)
        out.write(' [', autoline=False)
        prompts = responses.values()
        for choice in prompts[:-1]:
            out.write(autoline=False, *choice[1:])
            out.write(out.reset, '/', autoline=False)
        out.write(autoline=False, *prompts[-1][1:])
        out.write(out.reset, ']', autoline=False)
        if default_answer is not None:
            out.write(' (default: ', autoline=False)
            out.write(autoline=False, *default_answer_name)
            out.write(')', autoline=False)
        out.write(': ', autoline=False)
        try:
            response = raw_input()
        except EOFError:
            out.write("\nNot answerable: EOF on STDIN")
            raise_from(NoChoice())
        except IOError as e:
            if e.errno == errno.EBADF:
                out.write("\nNot answerable: STDIN is either closed, or not readable")
                raise_from(NoChoice())
            raise
        if not response:
            return default_answer
        results = set(
            (key, value) for key, value in responses.iteritems()
            if key[:len(response)].lower() == response.lower())
        if not results:
            err.write('Sorry, response "%s" not understood.' % (response,))
        elif len(results) > 1:
            err.write('Response "%s" is ambiguous (%s)' % (
                    response, ', '.join(key for key, val in results)))
        else:
            return list(results)[0][1][0]

    raise NoChoice()


class use_expand_filter(object):

    def __init__(self, use_expand, use_expand_hidden):
        """
        :type use_expand: iterable of strings
        :param use_expand: names of use-expanded variables.
        :type use_expand_hidden: set of strings
        :param use_expand_hidden: names of use-expanded vars that should not
            be added to the dict.
        """
        self.expand_filters = dict((x.lower(), (x not in use_expand_hidden, x))
            for x in use_expand)
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

        # XXX: note this is fairly slow- actually takes up more time then chunks of
        # the resolver
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


class Formatter(object):

    """Base Formatter class: All formatters should be subclasses of this."""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def iuse_strip(self, flags):
        """helper for stripping IUSE default chars"""
        for flag in flags:
            flag = flag.lstrip('+-')
            yield flag

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


class PkgcoreFormatter(Formatter):
    """The original pkgcore output"""
    def format(self, op):
        repo = getattr(op.pkg.repo, 'repo_id', None)
        if not repo:
            p = str(op.pkg.cpvstr)
        else:
            p = "%s::%s" % (op.pkg.cpvstr, repo)
        if op.desc == "replace":
            self.out.write("replace %s, %s" % (op.old_pkg.cpvstr, p))
        else:
            self.out.write("%s %s" % (op.desc.ljust(7), p))

class EmptyDict(object):

    def __getitem__(self, k):
        return k

    def __setitem__(self, k, v):
        pass

    def __delitem__(self, k):
        pass

class CountingFormatter(Formatter):

    """Subclass for formatters that count packages"""

    mappings = EmptyDict()

    def __init__(self, **kwargs):
        kwargs.setdefault("verbose", False)
        Formatter.__init__(self, **kwargs)
        self.package_data = defaultdictkey(lambda x:0)

        # total download size for all pkgs to be merged
        self.download_size = 0

    def visit_op(self, op_type):
        self.package_data[op_type] += 1

    def end(self):
        self.out.write()
        if self.verbose:
            total = sum(self.package_data.itervalues())
            self.out.write(
                'Total: %d package%s' % (total, 's'[total==1:]),
                autoline=False)

            d = dict(self.package_data.iteritems())
            op_types = [
                        ('add', 'new'),
                        ('upgrade', 'upgrade'),
                        ('downgrade', 'downgrade'),
                        ('slotted_add', 'in new slot'),
                        ('replace', 'reinstall')
                       ]
            op_list = []
            for op_type, op_str in op_types:
                num_ops = d.pop(op_type, 0)
                if num_ops:
                    if op_str == 'new':
                        op_list.append('%i %s' % (num_ops, op_str))
                    else:
                        op_list.append('%i %s%s' % (num_ops, op_str, 's'[num_ops==1:]))
            if d:
                op_list.append('%i other op%s' % (len(d), 's'[len(d)==1:]))
            if op_list:
                self.out.write(' (' + ', '.join(op_list) + ')', autoline=False)
            if self.download_size:
                self.out.write(', Size of downloads: ', sizeof_fmt(self.download_size), autoline=False)
            self.out.write()


class PortageFormatter(CountingFormatter):

    """Portage formatter

    A Formatter designed to resemble Portage's output
    as much as much as possible.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("use_expand", set())
        kwargs.setdefault("use_expand_hidden", set())
        CountingFormatter.__init__(self, **kwargs)
        self.use_splitter = use_expand_filter(self.use_expand,
            self.use_expand_hidden)
        # Map repo location to an index.
        self.repos = {}

        # set of files to be downloaded
        self.downloads = set()

    def format(self, op):
        # <type>       - ebuild, block or nomerge (for --tree)
        #        N     - new package
        #         R    - rebuild package
        #          F   - fetch restricted
        #          f   - fetch restricted already downloaded
        #           D  - downgrade
        #            U - updating to another version
        # Caveats:
        # - U and D are both displayed to show a downgrade - this is kept
        # in order to be consistent with existing portage behaviour

        out = self.out
        origautoline = out.autoline
        out.autoline = False

        self.pkg_disabled_use = self.pkg_forced_use = []
        if hasattr(self, 'disabled_use'):
            self.pkg_disabled_use = self.disabled_use.pull_data(op.pkg)
        if hasattr(self, 'forced_use'):
            self.pkg_forced_use = self.forced_use.pull_data(op.pkg)

        # This is for the summary at the end
        if self.quiet_repo_display:
            reponr = self.repos.setdefault(op.pkg.repo, len(self.repos) + 1)

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
            fetched = [out.fg('red'), out.bold, 'F', out.reset]
            for fetchable in op.pkg.fetchables:
                if not os.path.isfile(pjoin(self.distdir, fetchable.filename)):
                    break
                fetched = [out.fg('green'), out.bold, 'f', out.reset]
            op_chars[3] = fetched

        if op.desc == "add":
            op_chars[1] = [out.fg('green'), out.bold, 'N', out.reset]
            if op.pkg.slot != '0' and self.livefs_repos.match(op.pkg.unversioned_atom):
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
            logger.warning("unformattable op type: desc(%r), %r", (op.desc, op))

        out.write(*(iflatten_instance(op_chars)))
        out.write('] ')

        self.visit_op(op_type)

        pkg = [op.pkg.cpvstr]
        if self.verbose:
            if op.pkg.subslot != op.pkg.slot:
                pkg.append(':%s/%s' % (op.pkg.slot, op.pkg.subslot))
            elif op.pkg.slot != '0':
                pkg.append(':%s' % op.pkg.slot)
            if not self.quiet_repo_display and op.pkg.source_repository and \
                    op.pkg.source_repository != 'gentoo' or \
                    (op.desc == 'replace' and op_type != 'replace' and \
                     op.pkg.source_repository != op.old_pkg.source_repository):
                pkg.append("::%s" % op.pkg.source_repository)
        out.write(*(pkg_coloring + pkg + [out.reset]))

        installed = None
        if op.desc == 'replace' and op_type != 'replace':
            old_pkg = [op.old_pkg.fullver]
            if self.verbose:
                if op.old_pkg.subslot != op.old_pkg.slot:
                    old_pkg.append(':%s/%s' % (op.old_pkg.slot, op.old_pkg.subslot))
                elif op.old_pkg.slot != '0':
                    old_pkg.append(':%s' % op.old_pkg.slot)
                if not self.quiet_repo_display and op.old_pkg.source_repository and \
                        op.old_pkg.source_repository != 'gentoo' or \
                        op.pkg.source_repository != op.old_pkg.source_repository:
                    old_pkg.append("::%s" % op.old_pkg.source_repository)
            installed = ''.join(old_pkg)
        elif op_type == 'slotted_add':
            if self.verbose:
                pkgs = sorted(['%s:%s' % (x.fullver, x.slot) for x in \
                               self.livefs_repos.match(op.pkg.unversioned_atom)])
            else:
                pkgs = sorted([x.fullver for x in \
                               self.livefs_repos.match(op.pkg.unversioned_atom)])
            installed = ', '.join(pkgs)

        if installed:
            out.write(' ', out.fg('blue'), out.bold, '[%s]' % installed, out.reset)

        # Build a list of (useflags, use_expand_dicts) tuples.
        # HACK: if we are in "replace" mode we build a list of length
        # 4, else this is a list of length 2. We then pass this to
        # format_use which can take either 2 or 4 arguments.
        uses = ((), ())
        if op.desc == 'replace':
            uses = (self.iuse_strip(op.pkg.iuse), op.pkg.use,
                self.iuse_strip(op.old_pkg.iuse), op.old_pkg.use)
        elif op.desc == 'add':
            uses = (self.iuse_strip(op.pkg.iuse), op.pkg.use)
        stuff = map(self.use_splitter, uses)

        # Convert the list of tuples to a list of lists and a list of
        # dicts (both length 2 or 4).
        uselists, usedicts = zip(*stuff)
        self.format_use('use', *uselists)
        for expand in sorted(self.use_expand-self.use_expand_hidden):
            flaglists = [d.get(expand, ()) for d in usedicts]
            self.format_use(expand, *flaglists)

        if self.verbose:
            if not op.pkg.built:
                downloads = set(f.filename for f in op.pkg.fetchables
                    if not os.path.isfile(pjoin(self.distdir, f.filename)))
                if downloads.difference(self.downloads):
                    self.downloads.update(downloads)
                    size = sum(v.size for dist, v in
                               op.pkg.manifest.distfiles.iteritems() if dist in downloads)
                    if size:
                        self.download_size += size
                        out.write(' ', sizeof_fmt(size))

            if self.quiet_repo_display:
                out.write(out.fg('cyan'), " [%d]" % (reponr))

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
        if old_pkg_iuse is not None and old_pkg_use is not None:
            # updating or rebuilding pkg
            old_enabled = set(old_pkg_iuse) & set(old_pkg_use)
            old_disabled = set(old_pkg_iuse) - set(old_pkg_use)
            removed = set(old_pkg_iuse) - set(pkg_iuse)
            for flag in sorted(enabled):
                use_expand_flag = '_'.join((attr, flag)).lower() if attr != 'use' else None
                if flag in old_enabled:
                    # unchanged
                    if self.verbose:
                        if use_expand_flag in self.pkg_forced_use or \
                                use_expand_flag is None and flag in self.pkg_forced_use:
                            flags.extend(('(', red, bold, flag, reset, ')', ' '))
                        else:
                            flags.extend((red, bold, flag, reset, ' '))
                elif flag in old_disabled:
                    # toggled
                    if use_expand_flag in self.pkg_forced_use or \
                            use_expand_flag is None and flag in self.pkg_forced_use:
                        flags.extend(('(', green, bold, flag, reset, '*)', ' '))
                    else:
                        flags.extend((green, bold, flag, reset, '*', ' '))
                else:
                    # new
                    if use_expand_flag in self.pkg_forced_use or \
                            use_expand_flag is None and flag in self.pkg_forced_use:
                        flags.extend(('(', yellow, bold, flag, reset, '%*)', ' '))
                    else:
                        flags.extend((yellow, bold, flag, reset, '%*', ' '))
            for flag in sorted(disabled):
                use_expand_flag = '_'.join((attr, flag)).lower() if attr != 'use' else None
                if flag in old_disabled:
                    # unchanged
                    if self.verbose:
                        if use_expand_flag in self.pkg_disabled_use or \
                                use_expand_flag is None and flag in self.pkg_disabled_use:
                            flags.extend(('(', blue, bold, '-', flag, reset, ')', ' '))
                        else:
                            flags.extend((blue, bold, '-', flag, reset, ' '))
                elif flag in old_enabled:
                    # toggled
                    if use_expand_flag in self.pkg_disabled_use or \
                            use_expand_flag is None and flag in self.pkg_disabled_use:
                        flags.extend(('(', green, bold, '-', flag, reset, '*)', ' '))
                    else:
                        flags.extend((green, bold, '-', flag, reset, '*', ' '))
                else:
                    # new
                    if use_expand_flag in self.pkg_disabled_use or \
                            use_expand_flag is None and flag in self.pkg_disabled_use:
                        flags.extend(('(', yellow, bold, '-', flag, reset, '%)', ' '))
                    else:
                        flags.extend((yellow, bold, '-', flag, reset, '%', ' '))
            if self.verbose:
                for flag in sorted(removed):
                    if flag in old_enabled:
                        flags.extend(('(', yellow, bold, '-', flag, reset, '%*)', ' '))
                    else:
                        flags.extend(('(', yellow, bold, '-', flag, reset, '%)', ' '))
        else:
            # new pkg install
            for flag in sorted(enabled):
                use_expand_flag = '_'.join((attr, flag)).lower() if attr != 'use' else None
                if use_expand_flag in self.pkg_forced_use or \
                        use_expand_flag is None and flag in self.pkg_forced_use:
                    flags.extend(('(', red, bold, flag, reset, ')', ' '))
                else:
                    flags.extend((red, bold, flag, reset, ' '))
            for flag in sorted(disabled):
                use_expand_flag = '_'.join((attr, flag)).lower() if attr != 'use' else None
                if use_expand_flag in self.pkg_disabled_use or \
                        use_expand_flag is None and flag in self.pkg_disabled_use:
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
        out = self.out
        if self.verbose:
            super(PortageFormatter, self).end()
            out.write()
            if self.quiet_repo_display:
                repos = self.repos.items()
                repos.sort(key=operator.itemgetter(1))
                for k, v in repos:
                   reponame = getattr(k, 'repo_id', 'unknown repo id')
                   location = getattr(k, 'location', 'unspecified location')
                   if reponame != location:
                       self.out.write(' ', self.out.fg('cyan'), "[%d]" % v,
                           self.out.reset, " %s (%s)" % (reponame, location))
                   else:
                       self.out.write(' ', self.out.fg('cyan'), "[%d]" % v,
                           self.out.reset, " %s" % location)


class PaludisFormatter(CountingFormatter):

    """Paludis formatter

    A Formatter designed to resemble Paludis' output
    as much as much as possible.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("verbose", True)
        CountingFormatter.__init__(self, **kwargs)

    def format(self, op):
        out = self.out
        origautoline = out.autoline
        out.autoline = False

        out.write('* ')
        out.write(out.fg('blue'), op.pkg.key)
        out.write("-%s" % op.pkg.fullver)
        out.write("::%s " % op.pkg.repo.repo_id)
        out.write(out.fg('blue'), "{:%s} " % op.pkg.slot)
        op_type = op.desc
        if op.desc == 'add':
            suffix = 'N'
            if op.pkg.slot != '0':
                op_type = 'slotted_add'
                suffix = 'S'
            out.write(out.fg('yellow'), "[%s]" % suffix)
        elif op.desc == 'replace':
            if op.pkg != op.old_pkg:
                if op.pkg > op.old_pkg:
                    op_type = 'upgrade'
                else:
                    op_type = 'downgrade'
                out.write(out.fg('yellow'), "[%s %s]" % (
                        op_type[0].upper(), op.old_pkg.fullver))
            else:
                out.write(out.fg('yellow'), "[R]")
        else:
            # Shouldn't reach here
            logger.warning("unknown op type encountered: desc(%r), %r",
                (op.desc, op))
        self.visit_op(op_type)

        red = out.fg('red')
        green = out.fg('green')
        flags = []
        use = set(op.pkg.use)
        for flag in sorted(self.iuse_strip(op.pkg.iuse)):
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


def formatter_factory_generator(cls):
    """Factory for formatter factories that take no further arguments.

    A formatter factory is a subclass of Formatter or a callable
    taking the same keyword arguments.

    This helper wraps such a subclass in an extra no-argument callable
    that is usable by the configuration system.
    """
    @configurable(typename='pmerge_formatter')
    def factory():
        return cls
    return factory


basic_factory = formatter_factory_generator(BasicFormatter)
pkgcore_factory = formatter_factory_generator(PkgcoreFormatter)
portage_factory = formatter_factory_generator(PortageFormatter)
paludis_factory = formatter_factory_generator(PaludisFormatter)

@configurable(typename='pmerge_formatter')
def portage_verbose_factory():
    """Version of portage-formatter that is always in verbose mode."""
    def factory(**kwargs):
        kwargs['verbose'] = True
        return PortageFormatter(**kwargs)
    return factory

def sizeof_fmt(size):
    for x in ['B', 'kB', 'MB', 'GB']:
        if size < 1024.0:
            return "%3.1f %s" % (size, x)
        size /= 1024.0
    return "%3.1f %s" % (size, 'TB')
