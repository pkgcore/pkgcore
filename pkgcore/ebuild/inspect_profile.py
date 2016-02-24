# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD 3 clause

from snakeoil.cli import arghparse
from snakeoil.demandload import demandload

from pkgcore.ebuild import profiles
from pkgcore.util import commandline

demandload(
    'collections:defaultdict',
    'itertools:chain',
    'operator',
    'snakeoil.osutils:pjoin',
    'pkgcore.ebuild:atom',
)

commands = []
# info: keywords known
# global known flags, etc


class _base(arghparse.ArgparseCommand):

    @staticmethod
    def _validate_args(parser, namespace):
        path = namespace.profile
        if namespace.repo is not None and getattr(namespace.repo, 'location', False):
            if not path.startswith('/'):
                path = pjoin(namespace.repo.location, 'profiles', path)
        try:
            stack = profiles.ProfileStack(arghparse.existent_path(path))
        except ValueError as e:
            parser.error(e)
        if stack.node.repoconfig is None:
            parser.error("invalid profile path: '%s'" % path)
        namespace.profile = stack

    def bind_to_parser(self, parser):
        arghparse.ArgparseCommand.bind_to_parser(self, parser)
        parser.add_argument('profile', help='path to the profile to inspect')
        name = self.__class__.__name__
        kwds = {('_%s_suppress' % name): arghparse.DelayedDefault.wipe(('domain'), 50)}
        parser.set_defaults(**kwds)
        parser.bind_final_check(self._validate_args)
        self._subclass_bind(parser)

    def _subclass_bind(self, parser):
        """override to add more command line options"""


_register_command = commandline.register_command(commands)


class parent(_base):
    """output the linearized tree of inherited parents

    later lines override earlier lines
    """

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        out.write("\n".join(x.path for x in namespace.profile.stack))


class eapi(_base):
    """output EAPI support required for reading this profile"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        eapis = set(str(x.eapi) for x in namespace.profile.stack)
        out.write("\n".join(sorted(eapis)))


class status(_base):
    """output profile status"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        profiles_dir = pjoin(namespace.profile.node.repoconfig.location, 'profiles')
        profile_rel_path = namespace.profile.path[len(profiles_dir):].lstrip('/')
        arch_profiles = namespace.profile.node.repoconfig.arch_profiles
        statuses = [(path, status) for path, status in chain.from_iterable(arch_profiles.itervalues())
                    if path.startswith(profile_rel_path)]
        if len(statuses) > 1:
            for path, status in sorted(statuses):
                out.write('%s: %s' % (path, status))
        elif statuses:
            out.write(statuses[0][1])


class deprecated(_base):
    """dump deprecation notices, if any"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        for idx, profile in enumerate(x for x in namespace.profile.stack if x.deprecated):
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
    """output the system package set"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        for pkg in sorted(namespace.profile.system):
            out.write(str(pkg))


class use_expand(_base):
    """output the USE_EXPAND configuration for this profile

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
    """output the IUSE_EFFECTIVE value for this profile"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        if namespace.profile.iuse_effective:
            out.write(' '.join(sorted(namespace.profile.iuse_effective)))


class masks(_base):
    """inspect package masks"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        for mask in sorted(namespace.profile.masks):
            out.write(str(mask))


class unmasks(_base):
    """inspect package unmasks"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        for unmask in sorted(namespace.profile.unmasks):
            out.write(str(unmask))


class bashrcs(_base):
    """inspect bashrcs"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        for bashrc in namespace.profile.bashrcs:
            out.write(bashrc.path)


class keywords(_base):
    """inspect package.keywords"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        for pkg, keywords in namespace.profile.keywords:
            out.write('%s: %s' % (pkg, ' '.join(keywords)))


class accept_keywords(_base):
    """inspect package.accept_keywords"""

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
        global_use = []
        pkg_use = []

        for k, v in namespace.use.render_to_dict().iteritems():
            if isinstance(k, basestring):
                pkg, neg, pos = v[-1]
                if not isinstance(pkg, atom.atom):
                    continue
                neg = ('-' + x for x in neg)
                pkg_use.append((pkg, ' '.join(sorted(chain(neg, pos)))))
            else:
                _, neg, pos = v[0]
                neg = ('-' + x for x in neg)
                global_use = ' '.join(sorted(chain(neg, pos)))

        if global_use:
            out.write('*/*: %s' % (global_use,))
        if pkg_use:
            for pkg, use in sorted(pkg_use):
                out.write('%s: %s' % (pkg, use))


class use(_use):
    """inspect package.use flags"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        namespace.use = namespace.profile.pkg_use
        super(use, self).__call__(namespace, out, err)


class masked_use(_use):
    """inspect masked use flags"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        namespace.use = namespace.profile.masked_use
        super(masked_use, self).__call__(namespace, out, err)


class stable_masked_use(_use):
    """inspect stable masked use flags"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        namespace.use = namespace.profile.stable_masked_use
        super(stable_masked_use, self).__call__(namespace, out, err)


class forced_use(_use):
    """inspect forced use flags"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        namespace.use = namespace.profile.forced_use
        super(forced_use, self).__call__(namespace, out, err)


class stable_forced_use(_use):
    """inspect stable forced use flags"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        namespace.use = namespace.profile.stable_forced_use
        super(stable_forced_use, self).__call__(namespace, out, err)


class defaults(_base):
    """inspect defined configuration for this profile

    This is data parsed from make.defaults, containing things like
    ACCEPT_KEYWORDS.
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
    """output the arch defined for this profile"""

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        if namespace.profile.arch is not None:
            out.write(namespace.profile.arch)


def bind_parser(parser, name):
    subparsers = parser.add_subparsers(description="%s commands" % (name,))
    for command in commands:
        # Split docstrings into summaries and extended docs.
        help, _, docs = command.__doc__.partition('\n')
        subparser = subparsers.add_parser(
            command.__name__.lower(),
            help=help, docs=docs)
        command().bind_to_parser(subparser)
