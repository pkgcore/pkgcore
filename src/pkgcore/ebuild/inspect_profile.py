import argparse
import operator
from collections import defaultdict
from itertools import chain

from snakeoil.cli import arghparse
from snakeoil.osutils import pjoin
from snakeoil.sequences import split_negations

from ..util import commandline
from . import atom, profiles
from .misc import ChunkedDataDict

commands = []
# info: keywords known
# global known flags, etc


class _base(arghparse.ArgparseCommand):

    @staticmethod
    def _validate_args(parser, namespace):
        path = namespace.profile
        if path is None:
            if namespace.repo is not None:
                # default to the repo's main profiles dir
                path = pjoin(namespace.repo.location, 'profiles')
            else:
                # default to the configured system profile if none is selected
                path = namespace.config.get_default("domain").profile.profile
        else:
            if namespace.repo is not None and getattr(namespace.repo, 'location', False):
                if not path.startswith('/'):
                    path = pjoin(namespace.repo.location, 'profiles', path)
        try:
            stack = profiles.ProfileStack(arghparse.existent_path(path))
        except argparse.ArgumentTypeError as e:
            parser.error(e)
        if stack.node.repoconfig is None:
            parser.error(f"invalid profile path: {path!r}")
        namespace.profile = stack

    def bind_to_parser(self, parser):
        arghparse.ArgparseCommand.bind_to_parser(self, parser)
        parser.add_argument('profile', help='path to the profile to inspect')
        name = self.__class__.__name__
        kwds = {(f'_{name}_suppress'): arghparse.DelayedDefault.wipe(('domain'), 50)}
        parser.set_defaults(**kwds)
        parser.bind_final_check(self._validate_args)
        self._subclass_bind(parser)

    def _subclass_bind(self, parser):
        """override to add more command line options"""


_register_command = commandline.register_command(commands)


class parent(_base, metaclass=_register_command):
    """output the linearized tree of inherited parents

    later lines override earlier lines
    """

    def __call__(self, namespace, out, err):
        if namespace.repo is None:
            out.write("\n".join(x.path for x in namespace.profile.stack))
        else:
            repo_dir = pjoin(namespace.repo.location, 'profiles')
            for x in namespace.profile.stack:
                out.write(x.path[len(repo_dir):].lstrip('/'))


class eapi(_base, metaclass=_register_command):
    """output EAPI support required for reading this profile"""

    def __call__(self, namespace, out, err):
        eapis = set(str(x.eapi) for x in namespace.profile.stack)
        out.write("\n".join(sorted(eapis)))


class status(_base, metaclass=_register_command):
    """output profile status"""

    def __call__(self, namespace, out, err):
        profiles_dir = pjoin(namespace.profile.node.repoconfig.location, 'profiles')
        profile_rel_path = namespace.profile.path[len(profiles_dir):].lstrip('/')
        arch_profiles = namespace.profile.node.repoconfig.arch_profiles
        statuses = [(path, status) for path, status in chain.from_iterable(arch_profiles.values())
                    if path.startswith(profile_rel_path)]
        if len(statuses) > 1:
            for path, status in sorted(statuses):
                out.write(f'{path}: {status}')
        elif statuses:
            out.write(statuses[0][1])


class deprecated(_base, metaclass=_register_command):
    """dump deprecation notices, if any"""

    def __call__(self, namespace, out, err):
        for idx, profile in enumerate(x for x in namespace.profile.stack if x.deprecated):
            if idx:
                out.write()
            out.write(out.bold, out.fg("cyan"), profile.path, out.reset, ":")
            data = profile.deprecated
            if data[0]:
                out.write(" ", out.fg("yellow"), "replacement profile", out.reset, f": {data[0]}")
            if data[1]:
                out.write(" ", out.fg("yellow"), "deprecation message", out.reset, ":")
                for line in data[1].split("\n"):
                    out.write(line, prefix='  ')


class provided(_base, metaclass=_register_command):
    """list all package.provided packages

    Note that these are exact versions- if a dep requires a higher version,
    it's not considered satisfied.
    """

    def __call__(self, namespace, out, err):
        targets = defaultdict(list)
        for pkg in namespace.profile.provides_repo:
            targets[pkg.key].append(pkg)

        for pkg_name, pkgs in sorted(targets.items(), key=operator.itemgetter(0)):
            out.write(
                out.fg("cyan"), pkg_name, out.reset, ": ",
                ", ".join(x.fullver for x in sorted(pkgs)))


class system(_base, metaclass=_register_command):
    """output the system package set"""

    def __call__(self, namespace, out, err):
        for pkg in sorted(namespace.profile.system):
            out.write(str(pkg))


class use_expand(_base, metaclass=_register_command):
    """output the USE_EXPAND configuration for this profile

    Outputs two fields of interest; USE_EXPAND (pseudo use groups), and
    USE_EXPAND_HIDDEN which is immutable by user configuration and use deps
    (primarily used for things like setting the kernel or OS type).
    """

    def __call__(self, namespace, out, err):
        out.write(
            "flags: ",
            ', '.join(sorted(namespace.profile.use_expand)))
        out.write(
            "hidden: ",
            ', '.join(sorted(namespace.profile.use_expand_hidden)))


class iuse_effective(_base, metaclass=_register_command):
    """output the IUSE_EFFECTIVE value for this profile"""

    def __call__(self, namespace, out, err):
        if namespace.profile.iuse_effective:
            out.write(' '.join(sorted(namespace.profile.iuse_effective)))


class masks(_base, metaclass=_register_command):
    """inspect package masks"""

    def __call__(self, namespace, out, err):
        for mask in sorted(namespace.profile.masks):
            out.write(str(mask))


class unmasks(_base, metaclass=_register_command):
    """inspect package unmasks"""

    def __call__(self, namespace, out, err):
        for unmask in sorted(namespace.profile.unmasks):
            out.write(str(unmask))


class bashrcs(_base, metaclass=_register_command):
    """inspect bashrcs"""

    def __call__(self, namespace, out, err):
        for bashrc in namespace.profile.bashrcs:
            out.write(bashrc.path)


class keywords(_base, metaclass=_register_command):
    """inspect package.keywords"""

    def __call__(self, namespace, out, err):
        for pkg, keywords in namespace.profile.keywords:
            out.write(f"{pkg}: {' '.join(keywords)}")


class accept_keywords(_base, metaclass=_register_command):
    """inspect package.accept_keywords"""

    def __call__(self, namespace, out, err):
        for pkg, keywords in namespace.profile.accept_keywords:
            out.write(pkg, autoline=False)
            if keywords:
                out.write(f": {' '.join(keywords)}")
            else:
                out.write()


class _use(_base):

    def _output_use(self, neg, pos):
        neg = ('-' + x for x in neg)
        return ' '.join(sorted(chain(neg, pos)))

    def __call__(self, namespace, out, err):
        global_use = []
        pkg_use = {}

        for k, v in namespace.use.render_to_dict().items():
            if isinstance(k, str):
                for pkg, neg, pos in v:
                    if isinstance(pkg, atom.atom):
                        pkg_neg, pkg_pos = pkg_use.setdefault(pkg, (set(), set()))
                        pkg_neg.update(neg)
                        pkg_pos.update(pos)
                        matched = pkg_neg.intersection(pkg_pos)
                        pkg_pos.difference_update(matched)
                        pkg_neg.difference_update(matched)
            else:
                _, neg, pos = v[0]
                global_use = (neg, pos)

        if global_use:
            out.write(f'*/*: {self._output_use(*global_use)}')
        if pkg_use:
            for pkg, (neg, pos) in sorted(pkg_use.items()):
                if neg or pos:
                    out.write(f'{pkg}: {self._output_use(neg, pos)}')


class use(_use, metaclass=_register_command):
    """inspect enabled USE flags

    Including USE, USE_EXPAND, and package.use settings.
    """

    def __call__(self, namespace, out, err):
        u = ChunkedDataDict()
        u.add_bare_global(*split_negations(namespace.profile.use))
        u.merge(namespace.profile.pkg_use)
        namespace.use = u
        super().__call__(namespace, out, err)


class masked_use(_use, metaclass=_register_command):
    """inspect masked use flags"""

    def __call__(self, namespace, out, err):
        namespace.use = namespace.profile.masked_use
        super().__call__(namespace, out, err)


class stable_masked_use(_use, metaclass=_register_command):
    """inspect stable masked use flags"""

    def __call__(self, namespace, out, err):
        namespace.use = namespace.profile.stable_masked_use
        super().__call__(namespace, out, err)


class forced_use(_use, metaclass=_register_command):
    """inspect forced use flags"""

    def __call__(self, namespace, out, err):
        namespace.use = namespace.profile.forced_use
        super().__call__(namespace, out, err)


class stable_forced_use(_use, metaclass=_register_command):
    """inspect stable forced use flags"""

    def __call__(self, namespace, out, err):
        namespace.use = namespace.profile.stable_forced_use
        super().__call__(namespace, out, err)


class defaults(_base, metaclass=_register_command):
    """inspect defined configuration for this profile

    This is data parsed from make.defaults, containing things like
    ACCEPT_KEYWORDS.
    """

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
            out.write(f'{key}="{val}"')


class arch(_base, metaclass=_register_command):
    """output the arch defined for this profile"""

    def __call__(self, namespace, out, err):
        if namespace.profile.arch is not None:
            out.write(namespace.profile.arch)


def bind_parser(parser, name):
    subparsers = parser.add_subparsers(description=f"{name} commands")
    for command in commands:
        # Split docstrings into summaries and extended docs.
        help, _, docs = command.__doc__.partition('\n')
        subparser = subparsers.add_parser(
            command.__name__.lower(),
            help=help, docs=docs)
        command().bind_to_parser(subparser)
