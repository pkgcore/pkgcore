# Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
# License: BSD/GPL2

from pkgcore.util import commandline

from snakeoil.demandload import demandload
demandload(globals(),
    'snakeoil:osutils',
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


class BaseCommand(commandline.ArgparseCommand):

    required_arg_count = 0
    has_optional_args = False
    arg_spec = ()

    def bind_to_parser(self, parser, compat=False):
        commandline.ArgparseCommand.bind_to_parser(self, parser)
        default_portageq_args(parser)
        if self.requires_root:
            if compat:
                parser.add_argument(dest="domain", metavar="root",
                    action=commandline.DomainFromPath,
                    help="the domain that lives at root will be used")
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
                    type=atom.atom, **kwds)
            else:
                parser.add_argument(token, help="%s to inspect" % (token,),
                    **kwds)

    def _check_values(self, options, args):

        min_arg_count = self.required_arg_count
        arg_len = len(args)

        if self.requires_root:
            # note the _; this is to bypass the default property
            # that loads the default domain if unspecified
            if options._domain is None:
                if not arg_len:
                    self.error("not enough arguments supplied")
                options._domain = self._handle_root_arg(options, args[0])
                args = args[1:]
                arg_len -= 1
            min_arg_count -= 1

        if options.use is not None:
            options.use = frozenset(options.use.split())
        else:
            options.use = options.domain.settings.get("USE", frozenset())

        args = self.rewrite_args(options, args)

        return options, args

    def _handle_root_arg(self, options, path):
        domains = list(commandline.find_domains_from_path(options.config, path))
        if len(domains) > 1:
            self.error("multiple domains at %r; "
                "please use --domain option instead.\nDomains found: %s" %
                (path, ", ".join(repr(x[0]) for x in domains)))
        elif len(domains) != 1:
            self.error("couldn't find any domains at %r" % (path,))
        # return just the domain instance- the name of that pair we don't care about
        return domains[0][1]

    def rewrite_args(self, options, args):
        if not args:
            return args
        arg_spec = [x for x in self.arg_spec if 'root' != x]
        arg_spec.extend(arg_spec[-1] for x in xrange(len(args) - len(self.arg_spec) + 1))

        l = []
        for atype, arg in zip(arg_spec, args):
            if atype == 'atom':
                l.append(self.make_atom(options.atom_kls, options.use, arg))
            else:
                l.append(arg)
        return tuple(l)

    def make_atom(self, atom_kls, use, arg):
        try:
            a = atom_kls(arg)
            # force expansion.
            a.restrictions
            if isinstance(a, atom.transitive_use_atom):
                # XXX: hack
                a = conditionals.DepSet(a.restrictions, atom.atom, True)
                a = a.evaluate_depset(use)
                a = AndRestriction(*a.restrictions)
        except atom.MalformedAtom, e:
            self.error("malformed argument %r: %s" % (arg, e))
        return a

    @classmethod
    def make_command(cls, arg_spec='', requires_root=True, bind=None):

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
        out.write(str(envvar_getter.get(x, default_get)(options.domain, x)))
    return 0

@BaseCommand.make_command("atom", bind=commands)
def has_version(options, out, err):
    """
    @param domain: L{pkgcore.config.domain.domain} instance
    @param atom_str: L{pkgcore.ebuild.atom.atom} instance
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
    @param domain: L{pkgcore.config.domain.domain} instance
    @param atom_str: L{pkgcore.ebuild.atom.atom} instance
    """
    out.write(_best_version(options.domain, options.atom, out))
    return 0

@BaseCommand.make_command("atom", bind=commands)
def match(options, out, err):
    """
    @param domain: L{pkgcore.config.domain.domain} instance
    @param atom_str: L{pkgcore.ebuild.atom.atom} instance
    """
    i = options.domain.all_livefs_repos.itermatch(options.atom,
        sorter=sorted)
    for pkg in i:
        out.write(str_pkg(pkg))
    return 0

@BaseCommand.make_command(bind=commands)
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
