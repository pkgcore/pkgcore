import os
from functools import partial

from snakeoil import osutils
from snakeoil.cli import arghparse

from ..restrictions.boolean import AndRestriction
from ..util import commandline, packages
from . import atom, conditionals
from .eapi import get_eapi


def str_pkg(pkg):
    pkg = packages.get_raw_pkg(pkg)
    # special casing; old style virtuals come through as the original pkg.
    if pkg.package_is_real:
        return pkg.cpvstr
    if hasattr(pkg, "actual_pkg"):
        return pkg.actual_pkg.cpvstr
    # icky, but works.
    return str(pkg.rdepend).lstrip("=")


def get_atom_kls(value):
    eapi = get_eapi(value)
    if eapi is None:
        raise ValueError(f"EAPI {value} isn't known/supported")
    return eapi.atom_kls

def default_portageq_args(parser):
    parser.add_argument("--eapi", dest='atom_kls', type=get_atom_kls,
        default=atom.atom,
        help="limit all operations to just what the given EAPI supports.")
    parser.add_argument("--use", default=None,
        help="override the use flags used for transititive USE deps- "
       "dev-lang/python[threads=] for example")


def make_atom(value):
    return arghparse.DelayedValue(partial(_render_atom, value), 100)

def _render_atom(value, namespace, attr):
    a = namespace.atom_kls(value)
    if isinstance(a, atom.transitive_use_atom):
        a.restrictions
        # XXX bit of a hack.
        a = conditionals.DepSet(a.restrictions, atom.atom, True)
        a = a.evaluate_depset(getattr(namespace, 'use', ()))
        a = AndRestriction(*a.restrictions)
    setattr(namespace, attr, a)


class BaseCommand(arghparse.ArgparseCommand):

    required_arg_count = 0
    has_optional_args = False
    arg_spec = ()

    def bind_to_parser(self, parser, compat=False):
        arghparse.ArgparseCommand.bind_to_parser(self, parser)
        default_portageq_args(parser)

        if self.requires_root:
            if compat:
                kwds = {}
                if self._compat_root_default:
                    kwds["nargs"] = "?"
                    kwds["default"] = self._compat_root_default
                parser.add_argument(
                    dest="domain", metavar="root",
                    action=commandline.DomainFromPath,
                    help="the domain that lives at root will be used", **kwds)
            else:
                mux = parser.add_mutually_exclusive_group()
                commandline._mk_domain(mux)
                mux.add_argument(
                    '--domain-at-root', action=commandline.DomainFromPath,
                    dest="domain", help="specify the domain to use via its root path")

        for token in self.arg_spec:
            kwds = {}
            if token[-1] in '+?*':
                kwds["nargs"] = token[-1]
                token = token[:-1]
            if token == 'atom':
                parser.add_argument(
                    'atom', help="atom to inspect",
                    type=make_atom, **kwds)
            else:
                parser.add_argument(
                    token, help=f"{token} to inspect", **kwds)

    @classmethod
    def make_command(cls, arg_spec='', requires_root=True, bind=None,
                     root_default=None, name=None, **kwds):
        kwds = dict(
            arg_spec=tuple(arg_spec.split()), requires_root=requires_root,
            _compat_root_default=root_default, **kwds)

        def internal_function(functor, name=name):
            class mycommand(BaseCommand):
                function = __call__ = staticmethod(functor)
                __doc__ = getattr(functor, '__doc__', None)
                locals().update(kwds)

            if name is None:
                name = functor.__name__
            mycommand.__name__ = name

            if bind is not None:
                bind.append(mycommand)
            return mycommand

        return internal_function


common_commands = []
query_commands = []
portageq_commands = []

@BaseCommand.make_command("variable+", bind=query_commands)
def env_var(options, out, err):
    """
    return configuration defined variables.
    """
    default_get = lambda d,k: d.settings.get(k, "")
    distdir_get = lambda d,k: d.settings["fetcher"].distdir
    envvar_getter = {"DISTDIR":distdir_get}
    for x in options.variable:
        val = envvar_getter.get(x, default_get)(options.domain, x)
        if not isinstance(val, str):
            val = ' '.join(val)
        out.write(str(val))
    return 0

@BaseCommand.make_command("variable+", bind=portageq_commands, name='envvar',
    root_default='/')
def portageq_envvar(options, out, err):
    """
    return configuration defined variables.  Use envvar2 instead, this will be removed.
    """
    return env_var.function(options, out, err)

@BaseCommand.make_command("variable+", bind=portageq_commands, name='envvar2')
def portageq_envvar2(options, out, err):
    """
    return configuration defined variables.
    """
    return env_var.function(options, out, err)


@BaseCommand.make_command("atom", bind=common_commands)
def has_version(options, out, err):
    """
    Return 0 if an atom is merged, 1 if not.
    """
    if options.atom in options.domain.all_installed_repos:
        return 0
    return 1


def _best_version(domain, restrict):
    try:
        p = max(domain.all_installed_repos.itermatch(restrict))
    except ValueError:
        # empty sequence.
        return ''
    return str_pkg(p)

@BaseCommand.make_command("atom+", bind=common_commands)
def mass_best_version(options, out, err):
    """
    multiple best_version calls.
    """
    for x in options.atom:
        out.write("%s:%s" %
            (x, _best_version(options.domain, x).rstrip()))
    return 0

@BaseCommand.make_command("atom", bind=common_commands)
def best_version(options, out, err):
    """
    Return the maximum visible version for a given atom.
    """
    out.write(_best_version(options.domain, options.atom))
    return 0


@BaseCommand.make_command("atom", bind=portageq_commands)
def match(options, out, err):
    """shorthand for `pquery --installed`"""
    i = options.domain.all_installed_repos.itermatch(options.atom, sorter=sorted)
    for pkg in i:
        out.write(str_pkg(pkg))
    return 0


@BaseCommand.make_command(bind=common_commands, root_default='/')
def get_repos(options, out, err):
    l = []
    for repo in options.domain.ebuild_repos_raw:
        repo_id = getattr(repo, 'repo_id', getattr(repo, 'location', None))
        l.append(repo_id)
    for x in sorted(set(l)):
        out.write(x)
    return 0


def find_profile_paths_by_repo_id(config, repo_id, fullpath=False):
    repo = config.repo.get(repo_id, None)
    if repo is not None and getattr(repo, 'location', None) is not None:
        profiles = repo.config.profiles.arch_profiles
        for arch in profiles.keys():
            for path, stability in profiles[arch]:
                if fullpath:
                    path = os.path.join(repo.location, 'profiles', path)
                yield path


@BaseCommand.make_command("repo_id", bind=query_commands)
def get_profiles(options, out, err):
    if options.repo_id == 'all':
        profiles = (
            profile for repo in options.domain.ebuild_repos_raw
            for profile in find_profile_paths_by_repo_id(
                options.config, repo.repo_id, fullpath=True))
    else:
        profiles = find_profile_paths_by_repo_id(options.config, options.repo_id)
    for x in sorted(set(profiles)):
        out.write(x)
    return 0


@BaseCommand.make_command("repo_id", bind=portageq_commands)
def get_repo_path(options, out, err):
    repo = options.config.repo.get(options.repo_id, None)
    if repo is not None and getattr(repo, 'location', None) is not None:
        out.write(repo.location)
        return 0
    return 1

get_repo_path = BaseCommand.make_command(
    "repo_id", bind=query_commands, name='get_repo_path')(get_repo_path.function)


@BaseCommand.make_command("repo_id", bind=portageq_commands)
def get_repo_news_path(options, out, err):
    repo = options.config.repo.get(options.repo_id, None)
    if repo is not None and getattr(repo, 'location', None) is not None:
        out.write(osutils.normpath(osutils.pjoin(repo.location, 'metadata', 'news')))
        return 0
    return 1


@BaseCommand.make_command("root? repo_id", bind=portageq_commands,
    requires_root=False, name='get_repo_news_path')
def portageq_get_repo_news_path(options, out, err):
    return get_repo_news_path.function(options, out, err)

def bind_parser(parser, compat=False, name='portageq'):
    subparsers = parser.add_subparsers(description=f"{name} commands")
    l = common_commands[:]
    if compat:
        l += portageq_commands
    else:
        l += query_commands

    for command in sorted(l, key=lambda x:x.__name__):
        subparser = subparsers.add_parser(
            command.__name__, help=command.__doc__, description=command.__doc__)
        command().bind_to_parser(subparser, compat=compat)
