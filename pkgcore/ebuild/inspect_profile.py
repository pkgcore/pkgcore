# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD 3 clause

from snakeoil.demandload import demandload

from pkgcore.util import commandline

demandload(
    'collections:defaultdict',
    'itertools:chain',
    'operator',
    'pkgcore.ebuild:atom,profiles',
)

commands = []
# changelog, once a changelog parser is available
# desc: possibly
# info: desc, keywords known, known profiles (possibly putting it elsewhere)
# global known flags, etc


def profile(value):
    return profiles.ProfileStack(commandline.existent_path(value))


class _base(commandline.ArgparseCommand):

    def bind_to_parser(self, parser):
        commandline.ArgparseCommand.bind_to_parser(self, parser)
        parser.add_argument("profile", help="path to the profile to inspect", type=profile)
        name = self.__class__.__name__
        kwds = {('_%s_suppress' % name): commandline.DelayedDefault.wipe(('domain'), 50)}
        parser.set_defaults(**kwds)
        self._subclass_bind(parser)

    def _subclass_bind(self, parser):
        pass


_register_command = commandline.register_command(commands)


class parent(_base):

    """output the linearized tree of inherited parents

    later lines override earlier lines"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        out.write("\n".join(x.path for x in namespace.profile.stack))


class eapi(_base):

    """output EAPI support required for reading this profile"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        eapis = set(x.eapi_obj.magic for x in namespace.profile.stack)
        out.write("\n".join(sorted(eapis)))


class deprecated(_base):

    """dump deprecation notices, if any"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        deprecated = [x for x in namespace.profile.stack if x.deprecated]
        for idx, profile in enumerate(deprecated):
            if idx:
                out.write()
            out.write(out.bold, out.fg("cyan"), profile.path, out.reset, ":")
            data = profile.deprecated
            if data[0]:
                out.write(" ", out.fg("yellow"), "replacement profile", out.reset, ": %s" % (data[0],))
            if data[1]:
                out.write(" ", out.fg("yellow"), "deprecation message", out.reset, ":")
                for line in data[1].split("\n"):
                    out.write(line, prefix='  ')


class provided(_base):

    """list all package.provided packages

    Note that these are exact versions- if a dep requires a higher version,
    it's not considered satisfied.
    """

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        targets = defaultdict(list)
        for pkg in namespace.profile.provides_repo:
            targets[pkg.key].append(pkg)

        for pkg_name, pkgs in sorted(targets.iteritems(), key=operator.itemgetter(0)):
            out.write(
                out.fg("cyan"), pkg_name, out.reset, ": ",
                ", ".join(x.fullver for x in sorted(pkgs)))


class system(_base):

    """Output the system package set."""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        for pkg in sorted(namespace.profile.system):
            out.write(str(pkg))


class use_expand(_base):

    """Output the USE_EXPAND configuration for this profile

    Outputs two fields of interest; USE_EXPAND (pseudo use groups), and
    USE_EXPAND_HIDDEN which is immutable by user configuration and use deps
    (primarily used for things like setting the kernel or OS type).
    """

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        out.write(
            "flags: ",
            ', '.join(sorted(namespace.profile.use_expand)))
        out.write(
            "hidden: ",
            ', '.join(sorted(namespace.profile.use_expand_hidden)))


class iuse_effective(_base):

    """Output the IUSE_EFFECTIVE value for this profile"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        if namespace.profile.iuse_effective:
            out.write(' '.join(sorted(namespace.profile.iuse_effective)))


class masks(_base):

    """Inspect package masks"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        for mask in sorted(namespace.profile.masks):
            out.write(str(mask))


class unmasks(_base):

    """Inspect package unmasks"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        for unmask in sorted(namespace.profile.unmasks):
            out.write(str(unmask))


class bashrcs(_base):

    """Inspect bashrcs"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        for bashrc in namespace.profile.bashrcs:
            out.write(bashrc.path)


class keywords(_base):

    """Inspect package.keywords"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        for pkg, keywords in namespace.profile.keywords:
            out.write('%s: %s' % (pkg, ' '.join(keywords)))


class accept_keywords(_base):

    """Inspect package.accept_keywords"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        for pkg, keywords in namespace.profile.accept_keywords:
            out.write(pkg, autoline=False)
            if keywords:
                out.write(': %s' % (' '.join(keywords)))
            else:
                out.write()


class _use(_base):

    def __call__(self, namespace, out, err):
        global_use = None
        pkg_use = []

        for k, v in self.use.render_to_dict().iteritems():
            if isinstance(k, basestring):
                pkg, use_neg, use_pos = v[-1]
                if not isinstance(pkg, atom.atom):
                    continue
                neg = ('-' + x for x in use_neg)
                pos = (x for x in use_pos)
                pkg_use.append((pkg, ', '.join(x for x in sorted(chain(neg, pos)))))
            else:
                _, global_use_neg, global_use_pos = v[0]
                neg = ('-' + x for x in global_use_neg)
                pos = (x for x in global_use_pos)
                global_use = ', '.join(x for x in sorted(chain(neg, pos)))

        if global_use is not None:
            out.write('GLOBAL: %s' % (global_use))
        if pkg_use:
            for pkg, use in sorted(pkg_use):
                out.write('%s: %s' % (pkg, use))


class use(_use):

    """Inspect package.use flags"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        self.use = namespace.profile.pkg_use
        super(use, self).__call__(namespace, out, err)


class masked_use(_use):

    """Inspect masked use flags"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        self.use = namespace.profile.masked_use
        super(masked_use, self).__call__(namespace, out, err)


class stable_masked_use(_use):

    """Inspect stable masked use flags"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        self.use = namespace.profile.stable_masked_use
        super(stable_masked_use, self).__call__(namespace, out, err)


class forced_use(_use):

    """Inspect forced use flags"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        self.use = namespace.profile.forced_use
        super(forced_use, self).__call__(namespace, out, err)


class stable_forced_use(_use):

    """Inspect stable forced use flags"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        self.use = namespace.profile.stable_forced_use
        super(stable_forced_use, self).__call__(namespace, out, err)


class defaults(_base):

    """Inspect defined configuration for this profile

    This is data parsed from make.defaults, containing things like ACCEPT_KEYWORDS.
    """

    __metaclass__ = _register_command

    def _subclass_bind(self, parser):
        parser.add_argument(
            "variables", nargs='*',
            help="if not specified, all settings are displayed"
                 ". If given, output is limited to just those settings if "
                 "they exist")

    def __call__(self, namespace, out, err):
        var_filter = namespace.variables
        if var_filter:
            var_filter = set(var_filter).__contains__
        else:
            var_filter = lambda x: True

        settings = namespace.profile.default_env
        vars = sorted(filter(var_filter, settings))
        for key in vars:
            val = settings[key]
            if not val:
                continue
            if isinstance(val, tuple):
                val = ' '.join(val)
            out.write('%s="%s"' % (key, val))


class arch(_base):

    """Output the arch defined for this profile"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        if namespace.profile.arch is not None:
            out.write(namespace.profile.arch)


_color_parent = commandline.mk_argparser(color=True, domain=False, add_help=False)


def bind_parser(parser, name):
    subparsers = parser.add_subparsers(help="%s commands" % (name,))
    for command in commands:
        subparser = subparsers.add_parser(
            command.__name__.lower(),
            help=command.__doc__.split('\n', 1)[0], parents=[_color_parent])
        command().bind_to_parser(subparser)
