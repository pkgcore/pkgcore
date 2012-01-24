# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# License: BSD/GPL2

from pkgcore.util import commandline

from snakeoil.demandload import demandload
demandload(globals(),
    'snakeoil:osutils,currying',
    "pkgcore.ebuild:atom,conditionals,eapi",
    "pkgcore.restrictions.boolean:AndRestriction",
    "pkgcore.util:packages",
)

def str_pkg(pkg):
    pkg = packages.get_raw_pkg(pkg)
    # special casing; old style virtuals come through as the original pkg.
    if pkg.package_is_real:
        return pkg.cpvstr
    if hasattr(pkg, "actual_pkg"):
        return pkg.actual_pkg.cpvstr
    # icky, but works.
    return str(pkg.rdepends).lstrip("=")


def get_atom_kls(value):
    eapi_obj = eapi.get_eapi(value)
    if eapi_obj is None:
        raise ValueError("eapi %s isn't known/supported" % (value,))
    return eapi_obj.atom_kls

def default_portageq_args(parser):
    parser.add_argument("--eapi", dest='atom_kls', type=get_atom_kls,
        default=atom.atom,
        help="limit all operations to just what the given eapi supports.")
    parser.add_argument("--use", default=None,
        help="override the use flags used for transititive USE deps- "
       "dev-lang/python[threads=] for example")


def make_atom(value):
    return commandline.DelayedValue(
        currying.partial(_render_atom, value),
        100)

def _render_atom(value, namespace, attr):
    a = namespace.atom_kls(value)
    if isinstance(a, atom.transitive_use_atom):
        a.restrictions
        # XXX bit of a hack.
        a = conditionals.DepSet(a.restrictions, atom.atom, True)
        a = a.evaluate_depset(getattr(namespace, 'use', ()))
        a = AndRestriction(*a.restrictions)
    setattr(namespace, attr, a)


class BaseCommand(commandline.ArgparseCommand):

    required_arg_count = 0
    has_optional_args = False
    arg_spec = ()

    def bind_to_parser(self, parser, compat=False):
        commandline.ArgparseCommand.bind_to_parser(self, parser)
        default_portageq_args(parser)
        if self.requires_root:
            if compat:
                kwds = {}
                if self._compat_root_default:
                    kwds["nargs"] = "?"
                    kwds["default"] = self._compat_root_default
                parser.add_argument(dest="domain", metavar="root",
                    action=commandline.DomainFromPath,
                    help="the domain that lives at root will be used", **kwds)
            else:
                mux = parser.add_mutually_exclusive_group()
                commandline._mk_domain(mux)
                mux.add_argument('--domain-at-root',
                    action=commandline.DomainFromPath,
                    dest="domain", help="specify the domain to use via it's root path")
        for token in self.arg_spec:
            kwds = {}
            if token[-1] in '+?*':
                kwds["nargs"] = token[-1]
                token = token[:-1]
            if token == 'atom':
                parser.add_argument('atom', help="atom to inspect",
                    type=make_atom, **kwds)
            else:
                parser.add_argument(token, help="%s to inspect" % (token,),
                    **kwds)

    @classmethod
    def make_command(cls, arg_spec='', requires_root=True, bind=None, root_default=None):

        kwds = dict(arg_spec=tuple(arg_spec.split()), requires_root=requires_root)

        class mycommand(BaseCommand):
            locals().update(kwds)

        # note that we're modifying a global scope var here.
        # we could require globals() be passed in, but that
        # leads to fun reference cycles
        #commandline_commands[functor.__name__] = (mycommand, functor)


        def internal_function(functor):
            mycommand.__name__ = functor.__name__
            mycommand.__call__ = staticmethod(functor)
            mycommand._compat_root_default = root_default
            if bind is not None:
                bind.append(mycommand)
            return mycommand

        return internal_function

commands = []

@BaseCommand.make_command("variable+", bind=commands)
def envvar(options, out, err):
    """
    return configuration defined variables
    """
    default_get = lambda d,k: d.settings.get(k, "")
    distdir_get = lambda d,k: d.settings["fetcher"].distdir
    envvar_getter = {"DISTDIR":distdir_get}
    for x in options.variable:
        val = envvar_getter.get(x, default_get)(options.domain, x)
        if not isinstance(val, basestring):
            val = ' '.join(val)
        out.write(str(val))
    return 0

@BaseCommand.make_command("atom", bind=commands)
def has_version(options, out, err):
    """
    @param domain: :obj:`pkgcore.config.domain.domain` instance
    @param atom_str: :obj:`pkgcore.ebuild.atom.atom` instance
    """
    if options.domain.all_livefs_repos.has_match(options.atom):
        return 0
    return 1

def _best_version(domain, restrict, out):
    try:
        p = max(domain.all_livefs_repos.itermatch(restrict))
    except ValueError:
        # empty sequence.
        return ''
    return str_pkg(p)

@BaseCommand.make_command("atom+", bind=commands)
def mass_best_version(options, out, err):
    """
    multiple best_version calls
    """
    for x in options.atom:
        out.write("%s:%s" %
            (x, _best_version(options.domain, x, out).rstrip()))
    return 0

@BaseCommand.make_command("atom", bind=commands)
def best_version(options, out, err):
    """
    @param domain: :obj:`pkgcore.config.domain.domain` instance
    @param atom_str: :obj:`pkgcore.ebuild.atom.atom` instance
    """
    out.write(_best_version(options.domain, options.atom, out))
    return 0

@BaseCommand.make_command("atom", bind=commands)
def match(options, out, err):
    """
    @param domain: :obj:`pkgcore.config.domain.domain` instance
    @param atom_str: :obj:`pkgcore.ebuild.atom.atom` instance
    """
    i = options.domain.all_livefs_repos.itermatch(options.atom,
        sorter=sorted)
    for pkg in i:
        out.write(str_pkg(pkg))
    return 0

@BaseCommand.make_command(bind=commands, root_default='/')
def get_repositories(options, out, err):
    l = []
    for k, repo in options.config.repo.iteritems():
        repo_id = getattr(repo, 'repo_id', None)
        if repo_id is not None:
            l.append(repo_id)
    for x in sorted(set(l)):
        out.write(x)
    return 0

def find_repo_by_repo_id(config, repo_id):
    for k, repo in config.repo.iteritems():
        if getattr(repo, 'repo_id', None) == repo_id:
            yield repo

@BaseCommand.make_command("repo_id", bind=commands)
def get_repository_path(options, out, err):
    for repo in find_repo_by_repo_id(options.config, options.repo_id):
        if getattr(repo, 'location', None) is not None:
            out.write(repo.location)
        return 0
    return 1

@BaseCommand.make_command("repo_id", bind=commands)
def get_repo_news_path(options, out, err):
    for repo in find_repo_by_repo_id(options.config, options.repo_id):
        if getattr(repo, 'location', None) is not None:
            out.write(osutils.normpath(
                osutils.pjoin(repo.location, 'metadata', 'news')))
        return 0
    return 1

def bind_parser(parser, compat=False, name='portageq'):
    subparsers = parser.add_subparsers(help="%s commands" % (name,))
    for command in commands:
        subparser = subparsers.add_parser(command.__name__,
            help=command.__doc__)
        command().bind_to_parser(subparser, compat=compat)
