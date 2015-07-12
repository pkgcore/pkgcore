# Copyright: 2015 Tim Harder <radhermit@gmail.com>
# License: BSD/GPL2

"""pkgcore info reporting utility"""

from snakeoil.demandload import demandload

from pkgcore.util import commandline

demandload(
    'os',
    'platform',
    'snakeoil.process:get_proc_count',
    'pkgcore.ebuild.atom:atom',
)

argparser = commandline.mk_argparser(
    description=__doc__.split('\n', 1)[0])
argparser.add_argument(
    "-v", "--verbose", action='count',
    help="show verbose output")


class Report(object):

    def __init__(self, options):
        self.columns = 80
        self.domain = options.domain
        self.verbose = options.verbose

        self.ebuild_repos = [
            x for x in self.domain.source_repos
            if getattr(x, 'repository_type', None) == 'source']

    def header(s):
        out.write('=' * columns)
        out.write(s)
        out.write('=' * columns)


class Packages(Report):
    pass


def info_main_new(options, out, err):
    report = Report(options)

    header('System info')
    out.write('Platform: %s' % platform.platform())
    out.write('Python: %s-%s' % (platform.python_implementation(), platform.python_version()))
    profile_repo = next(x.repo_id for x in ebuild_repos
                        if x.location == os.path.dirname(domain.profile.basepath))
    out.write(
        'Profile: %s:%s' %
        (profile_repo, domain.profile.profile.lstrip(domain.profile.basepath)))

    out.write()
    header('System packages')
    pkgs = (
        'app-shells/bash', 'dev-python/snakeoil', 'sys-apps/pkgcore',
        'sys-devel/gcc', 'sys-devel/binutils', 'virtual/libc',
    )
    for pkg in pkgs:
        if pkg == 'virtual/libc':
            # query vdb for actual C library installed
            match = domain.all_livefs_repos.match(atom(pkg))
            pkg = match[0].rdepends[0].cpvstr
        matches = domain.all_livefs_repos.match(atom(pkg))
        if matches:
            matches = ', '.join('%s::%s' % (x.version, x.source_repository) for x in matches)
        else:
            matches = '---'
        out.write('%s: %s' % (pkg, matches))

    out.write()
    header('Repos (sorted by priority, high to low)')
    repo_attrs = ('location', 'masters')
    # restricted to ebuild repos until binpkg repos get integrated into
    # repos.conf and have their own repo config objects
    for repo in ebuild_repos:
        out.write(repo.repo_id)
        for repo_attr in repo_attrs:
            attr = getattr(repo.raw_repo.config, repo_attr, None)
            if attr:
                if not isinstance(attr, basestring):
                    attr = ', '.join(x for x in attr)
                out.write('    %s: %s' % (repo_attr, attr))

    out.write()
    header('Settings')
    settings = (
        'ACCEPT_KEYWORDS', 'ACCEPT_LICENSE', 'FEATURES', 'CHOST', 'CFLAGS',
        'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS',
    )
    for k in settings:
        v = domain.settings.get(k, '---')
        if not isinstance(v, basestring):
            v = ', '.join(x for x in v)
        out.write('%s: %s' % (k, v))
    return 0


@argparser.bind_main_func
def info_main_old(options, out, err):
    domain = options.domain
    columns = 80

    def header(s):
        out.write('=' * columns)
        out.write(s)
        out.write('=' * columns)

    header('System info')
    out.write('Platform: %s' % platform.platform())
    out.write('Python: %s-%s' % (platform.python_implementation(), platform.python_version()))
    profile_repo = next(x.repo_id for x in domain.ebuild_repos
                        if x.location == os.path.dirname(domain.profile.basepath))
    out.write(
        'Profile: %s:%s' %
        (profile_repo, domain.profile.profile.lstrip(domain.profile.basepath)))

    out.write()
    header('System packages')
    pkgs = (
        'app-shells/bash', 'dev-python/snakeoil', 'sys-apps/pkgcore',
        'sys-devel/gcc', 'sys-devel/binutils', 'virtual/libc',
    )
    for pkg in pkgs:
        if pkg == 'virtual/libc':
            # query vdb for actual C library installed
            match = domain.all_livefs_repos.match(atom(pkg))
            pkg = match[0].rdepends[0].cpvstr
        matches = domain.all_livefs_repos.match(atom(pkg))
        if matches:
            matches = ', '.join('%s::%s' % (x.version, x.source_repository) for x in matches)
        else:
            matches = '---'
        out.write('%s: %s' % (pkg, matches))

    out.write()
    header('Repos (sorted by priority, high to low)')
    repo_attrs = ('location', 'masters')
    # restricted to ebuild repos until binpkg repos get integrated into
    # repos.conf and have their own repo config objects
    for repo in domain.ebuild_repos:
        out.write(repo.repo_id)
        for repo_attr in repo_attrs:
            attr = getattr(repo.raw_repo.config, repo_attr, None)
            if attr:
                if not isinstance(attr, basestring):
                    attr = ', '.join(x for x in attr)
                out.write('    %s: %s' % (repo_attr, attr))

    out.write()
    header('Settings')
    settings = (
        'ACCEPT_KEYWORDS', 'ACCEPT_LICENSE', 'FEATURES', 'CHOST', 'CFLAGS',
        'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS',
    )
    for k in settings:
        v = domain.settings.get(k, '---')
        if not isinstance(v, basestring):
            v = ', '.join(x for x in v)
        out.write('%s: %s' % (k, v))
    return 0
