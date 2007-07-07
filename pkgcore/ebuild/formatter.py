# Copyright: 2006 Charlie Shepherd <masterdriverz@gentoo.org>
# License: GPL2

"""PMerge formatting module

To add a new formatter, add the relevant class (which
should be a subclass of Formatter). Documentation is
a necessity - things can change/break easily between
versions. Then add the class name (_not_ an instance) to
the formatters dictionary - this will instantly make your
formatter available on the commandline.
"""

import operator

from pkgcore.config import configurable


class NoChoice(KeyboardInterrupt):
    """Raised by L{userquery} if no choice was made.

    HACK: this subclasses KeyboardInterrupt, so if you ignore this it
    should do something reasonable.
    """

def userquery(prompt, out, err, responses=None, default_answer=None, limit=3):
    """Ask the user to choose from a set of options.

    Displays a prompt and a set of responses, then waits for a
    response which is checked against the responses. If there is an
    unambiguous match the value is returned.

    If the user does not input a valid response after a number of
    tries L{NoChoice} is raised. You can catch this if you want to do
    something special. Because it subclasses C{KeyboardInterrupt}
    the default behaviour is to abort as if the user hit ctrl+c.

    @type prompt: C{basestring} or a tuple of things to pass to a formatter.
        XXX this is a crummy api but I cannot think of a better one supporting
        the very common case of wanting just a string as prompt.
    @type out: formatter.
    @type err: formatter.
    @type responses: mapping with C{basestring} keys and tuple values.
    @param responses: mapping of user input to function result.
        The first item in the value tuple is returned, the rest is passed to
        out.
        Defaults to::
        {
            'yes': (True, out.fg('green'), 'Yes'),
            'no': (False, out.fg('red'), 'No'),
        }
    @param default_answer: returned if there is no input
        (user just hits enter). Defaults to True if responses is unset,
        unused otherwise.
    @param limit: number of allowed tries.
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
        response = raw_input()
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
        @type  use_expand: iterable of strings
        @param use_expand: names of use-expanded variables.
        @type  use_expand_hidden: set of strings
        @param use_expand_hidden: names of use-expanded vars that should not
            be added to the dict.
        """
        self.expand_filters = dict((x.lower(), (x not in use_expand_hidden, x))
            for x in use_expand)
        self.use_expand = use_expand
        self.use_expand_hidden = use_expand_hidden
        self.known_flags = {}

    def __call__(self, use):
        """Split USE flags up into "normal" flags and use-expanded ones.
        @type  use: iterable of strings
        @param use: flags that are set.
        @rtype: sequence of strings, dict mapping a string to a list of strings
        @return: set of normal flags and a mapping from use_expand name to
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


class PortageFormatter(Formatter):

    """Portage formatter

    A Formatter designed to resemble Portage's output
    as much as much as possible.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("use_expand", set())
        kwargs.setdefault("use_expand_hidden", set())
        Formatter.__init__(self, **kwargs)
        self.use_splitter = use_expand_filter(self.use_expand,
            self.use_expand_hidden)
        # Map repo location to an index.
        self.repos = {}

    def format(self, op):
        # [<type> NRFDU]
        #  <type>       - ebuild, block or nomerge (for --tree)
        #         N     - New package
        #          R    - Rebuild package
        #           F   - Fetch restricted
        #            D  - Downgrade
        #             U - Upgrade
        # Caveats:
        # - U and D are both displayed to show a downgrade - this is kept
        # in order to be consistent with existing portage behaviour

        verbose = self.verbose

        out = self.out
        origautoline = out.autoline
        out.autoline = False

        # This is for the summary at the end
        reponr = self.repos.setdefault(
            getattr(op.pkg.repo, "repo_id", "<unknown>"),
            len(self.repos) + 1)

        # We don't do blockers or --tree stuff yet
        out.write('[ebuild ')

        # Order is important here - look at the above diagram
        type = op.desc
        if op.desc == "add":
            out.write(out.fg('green'), ' N')
            if op.pkg.slot != '0':
                out.write(out.fg('green'), 'S')
            else:
                out.write(' ')
        elif op.desc == "replace" and op.pkg == op.old_pkg:
            out.write(out.fg('yellow'), '  R')
        else:
            out.write('   ')
            type = 'upgrade'

        if 'fetch' in op.pkg.restrict:
            out.write(out.fg('red'), 'F')
        else:
            out.write(' ')
        if type == 'upgrade':
            if op.pkg.fullver != op.old_pkg.fullver:
                out.write(out.fg('cyan'), 'U')
                if op.pkg > op.old_pkg:
                    out.write(' ')
                else:
                    out.write(out.fg('blue'), 'D')
        else:
            out.write('  ')
        out.write('] ')

        out.write(out.fg('green'), '%s ' % op.pkg.cpvstr)

        if type == 'upgrade':
            out.write(out.fg('blue'), '[%s] ' % op.old_pkg.fullver)

        # Build a list of (useflags, use_expand_dicts) tuples.
        # HACK: if we are in "replace" mode we build a list of length
        # 4, else this is a list of length 2. We then pass this to
        # format_use which can take either 2 or 4 arguments.
        if op.desc == 'replace':
            uses = (op.pkg.iuse, op.pkg.use, op.old_pkg.iuse, op.old_pkg.use)
        else:
            uses = (op.pkg.iuse, op.pkg.use)
        stuff = map(self.use_splitter, uses)

        # Convert the list of tuples to a list of lists and a list of
        # dicts (both length 2 or 4).
        uselists, usedicts = zip(*stuff)
        self.format_use('use', *uselists)
        for expand in self.use_expand-self.use_expand_hidden:
            flaglists = [d.get(expand, ()) for d in usedicts]
            self.format_use(expand, *flaglists)

        if verbose:
            out.write(out.fg('blue'), " [%d]" % (reponr,))

        out.write('\n')
        out.autoline = origautoline

    def format_use(self, attr, selectable, choice, oldselectable=None,
               oldchoice=None):
        """Write the current selection from a set of flags to a formatter.

        @type  attr: string
        @param attr: the name of the setting.
        @type  selectable: set of strings
        @param selectable: the possible values.
        @type  choice: set of strings
        @param choice: the chosen values.
        @type  oldselectable: set of strings
        @param oldselectable: the values possible in the previous version.
        @type  oldchoice: set of strings
        @param oldchoice: the previously chosen values.
        """
        out = self.out
        red = out.fg('red')
        green = out.fg('green')
        blue = out.fg('blue')
        yellow = out.fg('yellow')

        flags = []
        enabled = set(selectable) & set(choice)
        disabled = set(selectable) - set(choice)
        if oldselectable is not None and oldchoice is not None:
            old_enabled = set(oldselectable) & set(oldchoice)
            old_disabled = set(oldselectable) - set(oldchoice)
            for flag in sorted(enabled):
                assert flag
                if flag in old_enabled:
                    # Unchanged flag.
                    flags.extend((red, flag, ' '))
                elif flag in old_disabled:
                    # Toggled.
                    # Trailing single space is important, we can pop it below.
                    flags.extend((green, flag, '*', ' '))
                else:
                    # Flag did not exist earlier.
                    flags.extend((yellow, flag, '%', ' '))
            for flag in sorted(disabled | (set(oldselectable) - set(selectable))):
                assert flag
                if flag not in disabled:
                    # Removed flag.
                    flags.extend((yellow, '(-', flag, '%)', ' '))
                elif flag in old_disabled:
                    # Unchanged.
                    flags.extend((blue, '-', flag, ' '))
                elif flag in old_enabled:
                    # Toggled.
                    flags.extend((yellow, '-', flag, '*', ' '))
                else:
                    # New.
                    flags.extend((yellow, '-', flag, '%', ' '))
        else:
            for flag in sorted(enabled):
                flags.extend((red, flag, ' '))
            for flag in sorted(disabled):
                flags.extend((yellow, '-', flag, ' '))

        # Only write this if we have something to write
        if flags:
            out.write(attr.upper(), '="')
            # Omit the final space.
            out.write(*flags[:-1])
            out.write('" ')

    def end(self):
        if self.verbose:
            self.out.write()
            repos = self.repos.items()
            repos.sort(key=operator.itemgetter(1))
            for k, v in repos:
                self.out.write(self.out.fg('blue'), "[%d] %s" % (v, k))


class PaludisFormatter(Formatter):

    """Paludis formatter

    A Formatter designed to resemble Paludis' output
    as much as much as possible.
    """

    def __init__(self, **kwargs):
        Formatter.__init__(self, **kwargs)
        self.packages = self.new = self.upgrades = self.downgrades = 0
        self.nslots = 0

    def format(self, op):
        out = self.out
        origautoline = out.autoline
        out.autoline = False
        self.packages += 1

        out.write('* ')
        out.write(out.fg('blue'), op.pkg.key)
        out.write("-%s" % op.pkg.fullver)
        out.write("::%s " % op.pkg.repo.repo_id)
        out.write(out.fg('blue'), "{:%s} " % op.pkg.slot)
        if op.desc == 'add':
            if op.pkg.slot != '0':
                suffix = 'S'
                self.nslots += 1
            else:
                suffix = 'N'
                self.new += 1
            out.write(out.fg('yellow'), "[%s]" % suffix)
        elif op.desc == 'replace':
            if op.pkg != op.old_pkg:
                if op.pkg > op.old_pkg:
                    suffix = "U"
                    self.upgrades += 1
                else:
                    suffix = "D"
                    self.downgrades += 1
                out.write(out.fg('yellow'), "[%s %s]" % (
                        suffix, op.old_pkg.fullver))
            else:
                out.write(out.fg('yellow'), "[R]")

        red = out.fg('red')
        green = out.fg('green')
        flags = []
        use = set(op.pkg.use)
        for flag in sorted(op.pkg.iuse):
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

    def end(self):
        self.out.write(
            'Total: %d packages '
            '(%d new, %d upgrades, %d downgrades, %d in new slots)' % (
                self.packages, self.new, self.upgrades, self.downgrades,
                self.nslots))


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
