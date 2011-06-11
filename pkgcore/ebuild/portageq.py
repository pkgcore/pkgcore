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


commandline_commands = {}

class BaseCommand(commandline.OptionParser):

    required_arg_count = 0
    has_optional_args = False
    arguments_allowed = True
    enable_domain_options = False
    arg_spec = ()

    def _register_options(self):
        self.add_option("--eapi", default=None,
            help="limit all operations to just what the given eapi supports.")
        self.add_option("--use", default=None,
            help="override the use flags used for transititive USE deps- "
            "dev-lang/python[threads=] for example")

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

        if options.eapi is not None:
            eapi_obj = eapi.get_eapi(options.eapi)
            if eapi_obj is None:
                self.error("--eapi value %r isn't a known eapi" % (options.eapi,))
            options.atom_kls = eapi_obj.atom_kls
        else:
            options.atom_kls = atom.atom

        if options.use is not None:
            options.use = frozenset(options.use.split())
        else:
            options.use = options.domain.settings.get("USE", frozenset())

        if arg_len < min_arg_count or \
            (not self.has_optional_args and arg_len > min_arg_count):
            if self.requires_root:
                self.error("wrong arg count; expected %i non root argument(s), got %i" %
                    (min_arg_count, arg_len))
            self.error("wrong arg count; requires %i, got %i" %
                (self.required_arg_count, arg_len))

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


def make_command(arg_spec, **kwds):
    raw_arg_spec = arg_spec.split()
    arg_spec = ["<%s>" % (x,) for x in raw_arg_spec]
    try:
        arg_spec[arg_spec.index("<root>")] = "[<root> | --domain DOMAIN_NAME]"
        kwds["requires_root"] = True
    except ValueError:
        kwds["requires_root"] = False

    kwds["arg_spec"] = tuple(raw_arg_spec)

    takes_optional_args = kwds.pop("multiple_args", False)
    if "usage" not in kwds:
        txt = "%prog " + (" ".join(arg_spec))
        if takes_optional_args:
            txt += "+"
        kwds["usage"] = txt

    def internal_function(functor):

        class mycommand(BaseCommand):
            __doc__ = functor.__doc__
            required_arg_count = len(raw_arg_spec)
            has_optional_args = takes_optional_args
            enable_domain_options = True
            locals().update(kwds)
            arg_spec = tuple(raw_arg_spec)

        mycommand.__name__ = functor.__name__
        # note that we're modifying a global scope var here.
        # we could require globals() be passed in, but that
        # leads to fun reference cycles
        commandline_commands[functor.__name__] = (mycommand, functor)
        return mycommand

    return internal_function


@make_command("variable", multiple_args=True)
def envvar(options, out, err):
    """
    return configuration defined variables
    """
    default_get = lambda d,k: d.settings.get(k, "")
    distdir_get = lambda d,k: d.settings["fetcher"].distdir
    envvar_getter = {"DISTDIR":distdir_get}
    for x in options.arguments:
        out.write(str(envvar_getter.get(x, default_get)(options.domain, x)))
    return 0

@make_command("root atom", requires_root=True)
def has_version(options, out, err):
    """
    @param domain: L{pkgcore.config.domain.domain} instance
    @param atom_str: L{pkgcore.ebuild.atom.atom} instance
    """
    if options.domain.all_livefs_repos.has_match(options.arguments[0]):
        return 0
    return 1

def _best_version(domain, restrict, out):
    try:
        p = max(domain.all_livefs_repos.itermatch(restrict))
    except ValueError:
        # empty sequence.
        return ''
    return str_pkg(p)

@make_command("root atom", multiple_args=True, requires_root=True)
def mass_best_version(options, out, err):
    """
    multiple best_version calls
    """
    for x in options.arguments:
        out.write("%s:%s" %
            (x, _best_version(options.domain, x, out).rstrip()))
    return 0

@make_command("root atom", requires_root=True)
def best_version(options, out, err):
    """
    @param domain: L{pkgcore.config.domain.domain} instance
    @param atom_str: L{pkgcore.ebuild.atom.atom} instance
    """
    out.write(_best_version(options.domain, options.arguments[0], out))
    return 0

@make_command("root atom", requires_root=True)
def match(options, out, err):
    """
    @param domain: L{pkgcore.config.domain.domain} instance
    @param atom_str: L{pkgcore.ebuild.atom.atom} instance
    """
    i = options.domain.all_livefs_repos.itermatch(options.arguments[0],
        sorter=sorted)
    for pkg in i:
        out.write(str_pkg(pkg))
    return 0

@make_command("root")
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

@make_command("root repo_id")
def get_repository_path(options, out, err):
    for repo in find_repo_by_repo_id(options.config, options.arguments[0]):
        if getattr(repo, 'location', None) is not None:
            out.write(repo.location)
        return 0
    return 1

@make_command("root repo_id")
def get_repo_news_path(options, out, err):
    for repo in find_repo_by_repo_id(options.config, options.arguments[0]):
        if getattr(repo, 'location', None) is not None:
            out.write(osutils.normpath(
                osutils.pjoin(repo.location, 'metadata', 'news')))
        return 0
    return 1
