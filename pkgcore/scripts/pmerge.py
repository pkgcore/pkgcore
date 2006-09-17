# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""Mess with the resolver and vdb."""


import time

from pkgcore.restrictions import packages, values
from pkgcore.util import commandline, parserestrict, lists, repo_utils
from pkgcore.ebuild import resolver, atom
from pkgcore.repository import multiplex


class OptionParser(commandline.OptionParser):

    def __init__(self):
        commandline.OptionParser.__init__(self, description=__doc__)
        self.add_option('--deep', '-D', action='store_true')
        self.add_option('--unmerge', '-C', action='store_true')
        self.add_option('--upgrade', '-u', action='store_true')
        self.add_option('--set', '-s', action='append')
        self.add_option('--ignore-failures', action='store_true')
        self.add_option('--preload-vdb-state', action='store_true')
        self.add_option('--pretend', '-p', action='store_true')
        self.add_option('--fetchonly', '-f', action='store_true')
        self.add_option('--ignore-cycles', '-i', action='store_true')
        self.add_option('--nodeps', action='store_true')
        self.add_option('--replace', '-r', action='store_true')
        self.add_option('--usepkg', '-k', action='store_true')
        self.add_option('--usepkgonly', '-K', action='store_true')
        self.add_option('--pdb', action='store_true')
        self.add_option('--empty', '-e', action='store_true')
        self.add_option('--I-am-in-a-chroot', action='store_true',
                        dest='force')

    def check_values(self, options, args):
        options, args = commandline.OptionParser.check_values(
            self, options, args)
        options.targets = args

        if options.unmerge:
            if options.set:
                self.error("Sorry, using sets with -C probably isn't wise")
            if options.upgrade:
                self.error("can't combine upgrade and unmerging")
            if not options.targets:
                self.error("need at least one atom")
        if options.usepkgonly and options.usepkg:
            self.error('--usepkg is redundant when --usepkgonly is used')
        if not options.targets and not options.set:
            self.error('Need at least one atom/set')
        return options, ()


class AmbiguousQuery(parserestrict.ParseError):
    def __init__(self, token, keys):
        parserestrict.ParseError.__init__(
            self, '%s: multiple matches (%s)' % (token, ', '.join(keys)))
        self.token = token
        self.keys = keys

class NoMatches(parserestrict.ParseError):
    def __init__(self, token):
        parserestrict.ParseError.__init__(self, '%s: no matches' % (token,))

def parse_atom(token, repo, return_none=False):
    """Use L{parserestrict.parse_match} to produce a single atom.

    This matches the restriction against the repo, raises
    AmbiguousQuery if they belong to multiple cat/pkgs, returns an
    atom otherwise.

    @param token: string to convert.
    @param repo: L{pkgcore.prototype.tree} instance to search in.
    @param return_none: indicates if no matches raises or returns C{None}

    @return: an atom or C{None}.
    """
    # XXX this should be in parserestrict in some form, perhaps.
    ops, text = parserestrict.collect_ops(token)
    package = None
    if ops:
        l = text.rsplit("/", 1)
        restriction = parserestrict.parse_match("%sfoo/%s" % (ops, l[-1]))
        fullver = restriction.fullver
        if len(l) == 1:
            # force atom
            restriction = packages.PackageRestriction("package",
                values.StrExactMatch(package))
        else:
            restrict = parserestrict.parse_match("%s/%s" % 
                text[0], package)
    else:
        restriction = parserestrict.parse_match(token)
    key = None
    for match in repo.itermatch(restriction):
        if key is not None and key != match.key:
            raise AmbiguousQuery(token, (key, match.key))
        key = match.key
    if key is None:
        if return_none:
            return None
        raise NoMatches(token)
    if not ops:
        return atom.atom(key)
    return atom.atom("%s%s-%s" % (ops, key, fullver))


class Failure(ValueError):
    """Raised internally to indicate an "expected" failure condition."""


def unmerge(out, vdb, tokens, pretend=True, ignore_failures=False,
            force=False):
    """Unmerge tokens."""
    all_matches = set()
    for token in tokens:
        # Catch restrictions matching across more than one category.
        # Multiple matches in the same category are acceptable.

        # The point is that matching across more than one category is
        # nearly always unintentional ("pmerge -C spork" without
        # realising there are sporks in more than one category), but
        # matching more than one cat/pkg is impossible without
        # explicit wildcards.
        restriction = parserestrict.parse_match(token)
        matches = vdb.match(restriction)
        if not matches:
            raise Failure('Nothing matches %s' % (token,))
        categories = set(pkg.category for pkg in matches)
        if len(categories) > 1:
            raise parserestrict.ParseError(
                '%s matches in multiple categories (%s)' % (
                    token, ', '.join(set(pkg.key for pkg in matches))))
        all_matches.update(matches)

    matches = sorted(all_matches)
    out.write(out.bold, 'Unmerge:')
    out.prefix = [out.bold, ' * ', out.reset]
    for match in matches:
        out.write(match.cpvstr)
    out.prefix = []

    if pretend:
        return

    if vdb.frozen:
        if force:
            out.write(
                out.fg(out.red), out.bold,
                'warning: vdb is frozen, overriding')
            vdb.frozen = False
        else:
            raise Failure('vdb is frozen')

    for match in matches:
        op = vdb.uninstall(match)
        ret = op.finish()
        if not ret:
            if not ignore_failures:
                raise Failure('failed unmerging %s' % (token,))
            out.write(out.fg(out.red), 'failed unmerging ', token)


def write_error(out, message):
    # XXX should have a convenience thing on formatter for this.
    out.first_prefix = [out.fg('red'), out.bold, '!!! ', out.reset]
    out.later_prefix = out.first_prefix
    out.wrap = True
    out.write(message)
    out.wrap = False
    out.first_prefix = []
    out.later_prefix = []


def main(config, options, out, err):
    if options.debug:
        resolver.plan.limiters.add(None)

    domain = config.get_default('domain')
    vdb = domain.all_vdbs

    # This mode does not care about sets and packages so bypass all that.
    if options.unmerge:
        try:
            unmerge(
                out, vdb, options.targets, pretend=options.pretend,
                ignore_failures=options.ignore_failures, force=options.force)
        except (parserestrict.ParseError, Failure), e:
            write_error(out, str(e))
            return 1
        return

    repos = domain.all_repos
    if options.usepkgonly or options.usepkg:
        if options.usepkgonly:
            repos = [
                repo for repo in repos.trees
                if getattr(repo, 'format_magic', None) != 'ebuild_src']
        else:
            repos = [
                repo for repo in repos.trees
                if getattr(repo, 'format_magic', None) == 'ebuild_built'] + [
                repo for repo in repos.trees
                if getattr(repo, 'format_magic', None) != 'ebuild_built']
        repos = multiplex.tree(*repos)

    atoms = []
    for setname in options.set:
        try:
            pkgset = config.pkgset[setname]
        except KeyError:
            err.write('No set called %r!\n' % (setname,))
            return 1
        atoms.extend(list(pkgset))

    for token in options.targets:
        try:
            a = parse_atom(token, repos, return_none=True)
        except parserestrict.ParseError, e:
            write_error(out, str(e))
            return 1
        if a is None:
            if token in config.pkgset:
                write_error(
                    out, 'No package matches for %r, but there is a set with '
                    'that name. Use -s to specify a set.' % (token,))
                return 2
        else:
            atoms.append(a)

    atoms = lists.stable_unique(atoms)

    if options.upgrade:
        resolver_kls = resolver.upgrade_resolver
    else:
        resolver_kls = resolver.min_install_resolver

    extra_kwargs = {}
    if options.empty:
        extra_kwargs['resolver_cls'] = resolver.empty_tree_merge_plan

    resolver_inst = resolver_kls(
        vdb, repos, verify_vdb=options.deep, nodeps=options.nodeps,
        drop_cycles=options.ignore_cycles, force_replacement=options.replace,
        **extra_kwargs)

    if options.preload_vdb_state:
        out.write(out.bold, ' * ', out.reset, 'Preloading vdb... ')
        vdb_time = time.time()
        resolver_inst.load_vdb_state()
        vdb_time = time.time() - vdb_time
    else:
        vdb_time = 0.0

    failures = []
    resolve_time = time.time()
    out.write(out.bold, ' * ', out.reset, 'Resolving...')
    for restrict in atoms:
#        print "\ncalling resolve for %s..." % restrict
        ret = resolver_inst.add_atom(restrict)
        if ret:
            write_error(out, 'Resolver returned %r' % (ret,))
            write_error('resolution failed')
            failures.append(restrict)
            if not options.ignore_failures:
                break
    resolve_time = time.time() - resolve_time
    if failures:
        out.write()
        out.write('Failures encountered:')
        for restrict in failures:
            write_error(out, "failed '%s'" % (restrict,))
            out.write('potentials:')
            match_count = 0
            for r in repo_utils.get_raw_repos(repos):
                l = r.match(restrict)
                if l:
                    out.write(
                        "repo %s: [ %s ]" % (r, ", ".join(str(x) for x in l)))
                    match_count += len(l)
            if not match_count:
                out.write("no matches found in %s" % (repos,))
            out.write()
            if not options.ignore_failures:
                return 1

    out.write(out.bold, ' * ', out.reset, 'buildplan')
    plan = list(resolver_inst.state.iter_pkg_ops())
    changes = []
    for op, pkgs in plan:
        if pkgs[-1].repo.livefs and op != "replace":
            continue
        elif not pkgs[-1].package_is_real:
            continue
        changes.append((op, pkgs))
        out.write(
            "%s %s" % (
                op.ljust(8), ", ".join(str(y) for y in reversed(pkgs))))

    out.write()
    out.write('Success!')
    out.write(out.bold, '%.2f' % (resolve_time,), out.reset,
              ' seconds resolving')
    if vdb_time:
        out.write(out.bold, '%.2f' % (vdb_time,), out.reset,
                  ' seconds preloading vdb state')
    if options.pretend:
        return
    for op, pkgs in changes:
        out.write("processing %s" % (pkgs[0],))
        buildop = pkgs[0].build()
        if options.fetchonly:
            out.write("\n%i files required-" % len(pkgs[0].fetchables))
            try:
                ret = buildop.fetch()
            except (SystemExit, KeyboardInterrupt):
                raise
            except Exception, e:
                ret = e
        else:
            out.write("building...")
            built_pkg = buildop.finalize()
            if built_pkg is not False:
                out.write()
                out.write("merge op: %s %s" % (op, pkgs))
                if op == "add":
                    i = vdb.install(built_pkg)
                elif op == "replace":
                    i = vdb.replace(pkgs[1], built_pkg)
                ret = i.finish()
                buildop.clean()
            else:
                write_error(out, "failure building %s" % (pkgs[0],))
                if not options.ignore_failures:
                    return 1

            # force this explicitly- can hold onto a helluva lot more
            # then we would like.
            del built_pkg
        if ret != True:
            write_error(
                "got %s for a phase execution for %s" % (ret, pkgs[0]))
            if not options.ignore_failures:
                return 1
        elif not options.fetchonly:
            buildop.clean()
    return 0
