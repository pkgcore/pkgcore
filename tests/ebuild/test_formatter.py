import difflib

from snakeoil.test import TestCase
from snakeoil.test.argparse_helpers import (Bold, Color, FakeStreamFormatter,
                                            Reset)

from pkgcore.ebuild.atom import atom
from pkgcore.ebuild.formatter import (BasicFormatter, PaludisFormatter,
                                      PkgcoreFormatter, PortageFormatter)
from pkgcore.test.misc import FakePkg, FakeRepo


# These two are probably unnecessary with ferringb's changes to
# PkgcoreFormatter, but as he's the one that uses it there's no point fixing
# what ain't broke. --charlie
class FakeMutatedPkg(FakePkg):
    def __str__(self):
        # Yes this should be less hackish (and hardcoded values suck),
        # but we can't really subclass MutatedPkg so this will have to do
        return f"MutatedPkg(built ebuild: {self.cpvstr}, overrides=('depend', 'rdepend'))"

class FakeEbuildSrc(FakePkg):
    def __str__(self):
        # Yes this should be less hackish (and hardcoded values suck)
        # but we can't really subclass ebuild_src so this will have to do
        return f"config wrapped(use): ebuild src: {self.cpvstr}"


class FakeOp:
    def __init__(self, package, oldpackage=None, desc='add'):
        self.pkg = package
        if oldpackage:
            self.old_pkg = oldpackage
            self.desc = 'replace'
        else:
            self.desc = desc

class BaseFormatterTest:
    prefix = ()
    suffix = ('\n',)
    def setUp(self):
        self.fakeout = FakeStreamFormatter()
        self.fakeerr = FakeStreamFormatter()
        self.formatter = self.newFormatter()

    @property
    def verify_formatterClass(self):
        class state_verifying_class(self.formatterClass):
            def format(internal_self, *args, **kwds):
                autoline = self.fakeout.autoline
                try:
                    ret = self.formatterClass.format(internal_self, *args, **kwds)
                except Exception as e:
                    self.assertEqual(
                        autoline, self.fakeout.autoline,
                        msg="exception thrown {e}, autoline was {autoline}, now is {self.fakeout.autoline}")
                    raise
                self.assertEqual(
                    autoline, self.fakeout.autoline,
                    msg="autoline was {autoline}, now is {self.fakeout.autoline}")
                return ret
        return state_verifying_class

    def newFormatter(self, **kwargs):
        disable_method_checks = kwargs.pop("disable_method_checks", False)
        kwargs.setdefault("out", self.fakeout)
        kwargs.setdefault("err", self.fakeerr)
        if not disable_method_checks:
            kls = self.verify_formatterClass
        else:
            kls = self.formatterClass
        return kls(**kwargs)

    def assertOut(self, *args, **kwargs):

        stringlist = []
        objectlist = []

        args = list(args)

        prefix = kwargs.setdefault("prefix", self.prefix)
        if isinstance(prefix, tuple):
            args = list(prefix) + args
        elif isinstance(prefix, list):
            args = prefix + args
        else:
            args.insert(0, prefix)

        suffix = kwargs.setdefault("suffix", self.suffix)
        if isinstance(suffix, tuple):
            args = args + list(suffix)
        elif isinstance(suffix, list):
            args = args + suffix
        else:
            args.append(suffix)

        for arg in args:
            if isinstance(arg, str):
                stringlist.append(arg.encode('ascii'))
            elif isinstance(arg, bytes):
                stringlist.append(arg)
            else:
                objectlist.append(b''.join(stringlist))
                stringlist = []
                objectlist.append(arg)
        objectlist.append(b''.join(stringlist))

        # Hack because a list with an empty string in is True
        if objectlist == [b'']:
            objectlist = []

        self.assertEqual(self.fakeout.stream, objectlist, '\n' + '\n'.join(
                difflib.unified_diff(
                    list(repr(s) for s in objectlist),
                    list(repr(s) for s in self.fakeout.stream),
                    'expected', 'actual', lineterm='')))
        self.fakeout.resetstream()

    def test_end(self):
        # Sub-classes should override this if they print something in end()
        self.formatter.format(FakeOp(FakeMutatedPkg('dev-util/diffball-1.1')))
        self.fakeout.resetstream()
        self.formatter.end()
        self.assertOut(suffix=())


class TestBasicFormatter(BaseFormatterTest, TestCase):

    formatterClass = BasicFormatter

    def test_install(self):
        # Make sure we ignore versions...
        self.formatter.format(FakeOp(FakeMutatedPkg('dev-util/diffball-1.1')))
        self.assertOut('dev-util/diffball')

    def test_reinstall(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.4'),
            FakeMutatedPkg('app-arch/bzip2-1.0.4')))
        self.assertOut('app-arch/bzip2')


class TestPkgcoreFormatter(BaseFormatterTest, TestCase):

    formatterClass = PkgcoreFormatter

    def test_install(self):
        self.formatter.format(FakeOp(FakeEbuildSrc('dev-util/diffball-1.0')))
        self.assertOut("add     dev-util/diffball-1.0")

    def test_install_repo(self):
        self.formatter.format(FakeOp(FakeEbuildSrc('dev-util/diffball-1.0',
            repo=FakeRepo(repo_id='gentoo', location='/var/gentoo/repos/gentoo'))))
        self.assertOut("add     dev-util/diffball-1.0::gentoo")

    def test_reinstall(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('dev-util/diffball-1.2'),
                FakeMutatedPkg('dev-util/diffball-1.1')))
        self.assertOut(
            "replace dev-util/diffball-1.1, "
            "dev-util/diffball-1.2")

    def test_reinstall_repo(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('dev-util/diffball-1.2',
                   repo=FakeRepo(repo_id='gentoo', location='/var/gentoo/repos/gentoo')),
                FakeMutatedPkg('dev-util/diffball-1.1')))
        self.assertOut(
            "replace dev-util/diffball-1.1, "
            "dev-util/diffball-1.2::gentoo")


class CountingFormatterTest(BaseFormatterTest):

    endprefix = ""
    endsuffix = "\n"

    def newFormatter(self, **kwargs):
        kwargs.setdefault('verbosity', 1)
        return BaseFormatterTest.newFormatter(self, **kwargs)

    def assertEnd(self, *args, **kwargs):
        kwargs.setdefault('prefix', self.endprefix)
        kwargs.setdefault('suffix', self.endsuffix)
        BaseFormatterTest.assertOut(self, *args, **kwargs)

    def test_end(self):
        self.formatter.end()
        self.assertEnd('\nTotal: 0 packages')

    def test_end_new(self):
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6')))
        self.fakeout.resetstream()
        self.formatter.end()
        self.assertEnd('\nTotal: 1 package (1 new)')

    def test_end_new_multiple(self):
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6')))
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/gzip-1.6')))
        self.fakeout.resetstream()
        self.formatter.end()
        self.assertEnd('\nTotal: 2 packages (2 new)')

    def test_end_newslot(self):
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', slot='1')))
        self.fakeout.resetstream()
        self.formatter.end()
        self.assertEnd('\nTotal: 1 package (1 in new slot)')

    def test_end_newslot_multiple(self):
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', slot='1')))
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/gzip-1.6', slot='2')))
        self.fakeout.resetstream()
        self.formatter.end()
        self.assertEnd('\nTotal: 2 packages (2 in new slots)')

    def test_end_downgrade(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6'),
            FakeMutatedPkg('app-arch/bzip2-1.0.4')))
        self.fakeout.resetstream()
        self.formatter.end()
        self.assertEnd('\nTotal: 1 package (1 downgrade)')

    def test_end_downgrade_multiple(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6'),
            FakeMutatedPkg('app-arch/bzip2-1.0.4')))
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/gzip-1.5'),
            FakeMutatedPkg('app-arch/gzip-1.6')))
        self.fakeout.resetstream()
        self.formatter.end()
        self.assertEnd('\nTotal: 2 packages (2 downgrades)')

    def test_end_upgrade(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.4'),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6')))
        self.fakeout.resetstream()
        self.formatter.end()
        self.assertEnd('\nTotal: 1 package (1 upgrade)')

    def test_end_upgrade_multiple(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.4'),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6')))
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/gzip-1.6'),
            FakeMutatedPkg('app-arch/gzip-1.5')))
        self.fakeout.resetstream()
        self.formatter.end()
        self.assertEnd('\nTotal: 2 packages (2 upgrades)')

    def test_end_reinstall(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.4'),
            FakeMutatedPkg('app-arch/bzip2-1.0.4')))
        self.fakeout.resetstream()
        self.formatter.end()
        self.assertEnd('\nTotal: 1 package (1 reinstall)')

    def test_end_reinstall_multiple(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.4'),
            FakeMutatedPkg('app-arch/bzip2-1.0.4')))
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/gzip-1.6'),
            FakeMutatedPkg('app-arch/gzip-1.6')))
        self.fakeout.resetstream()
        self.formatter.end()
        self.assertEnd('\nTotal: 2 packages (2 reinstalls)')

    def test_end_all_ops_order(self):
        # new
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/pkga-1.0.3-r6')))
        # new slot
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/pkgb-1.0.3-r6', slot='1')))
        # downgrade
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/pkgc-1.0.3-r6'),
            FakeMutatedPkg('app-arch/pkgc-1.0.4')))
        # upgrade
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/pkgd-1.0.4'),
            FakeMutatedPkg('app-arch/pkgd-1.0.3-r6')))
        # reinstall
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/pkge-1.0.4'),
            FakeMutatedPkg('app-arch/pkge-1.0.4')))

        self.fakeout.resetstream()
        self.formatter.end()
        self.assertEnd(
            '\nTotal: 5 packages (1 new, 1 upgrade, 1 downgrade, 1 in new slot, 1 reinstall)')


class TestPaludisFormatter(CountingFormatterTest, TestCase):
    formatterClass = PaludisFormatter

    def setUp(self):
        BaseFormatterTest.setUp(self)
        self.repo = FakeRepo(repo_id='gentoo', location='/var/gentoo/repos/gentoo')

    def FakeEbuildSrc(self, *args, **kwargs):
        kwargs.setdefault("repo", self.repo)
        return FakeEbuildSrc(*args, **kwargs)

    def test_upgrade(self):
        self.formatter.format(
            FakeOp(self.FakeEbuildSrc('app-arch/bzip2-1.0.4'),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6')))
        self.assertOut("* ", Color('fg', 'blue'), "app-arch/bzip2-1.0.4::gentoo ",
            Color('fg', 'blue'), "{:0} ", Color('fg', 'yellow'), "[U 1.0.3-r6]")

    def test_downgrade(self):
        self.formatter.format(
            FakeOp(self.FakeEbuildSrc('app-arch/bzip2-1.0.3-r6'),
            FakeMutatedPkg('app-arch/bzip2-1.0.4')))
        self.assertOut("* ", Color('fg', 'blue'), "app-arch/bzip2-1.0.3-r6::gentoo ",
            Color('fg', 'blue'), "{:0} ", Color('fg', 'yellow'), "[D 1.0.4]")

    def test_reinstall(self):
        self.formatter.format(
            FakeOp(self.FakeEbuildSrc('app-arch/bzip2-1.0.3-r6'),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6')))
        self.assertOut("* ", Color('fg', 'blue'), "app-arch/bzip2-1.0.3-r6::gentoo ",
            Color('fg', 'blue'), "{:0} ", Color('fg', 'yellow'), "[R]")

    def test_nouse(self):
        self.formatter.format(
            FakeOp(self.FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['static']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6')))
        self.assertOut("* ", Color('fg', 'blue'), "app-arch/bzip2", "-1.0.3-r6", "::gentoo ",
            Color('fg', 'blue'), "{:0} ", Color('fg', 'yellow'), "[R] ",
            Color('fg', 'red'), "-static")

    def test_iuse_defaults(self):
        self.formatter.format(
            FakeOp(self.FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', eapi='1', iuse=['+static', '-junk'], use=['static']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6')))
        self.assertOut("* ", Color('fg', 'blue'), "app-arch/bzip2", "-1.0.3-r6", "::gentoo ",
            Color('fg', 'blue'), "{:0} ", Color('fg', 'yellow'), "[R] ",
            Color('fg', 'red'), "-junk ", Color('fg', 'green'), "static")

    def test_use(self):
        self.formatter.format(
            FakeOp(self.FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['static'], use=['static']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6')))
        self.assertOut("* ", Color('fg', 'blue'), "app-arch/bzip2", "-1.0.3-r6", "::gentoo ",
            Color('fg', 'blue'), "{:0} ", Color('fg', 'yellow'), "[R] ",
            Color('fg', 'green'), "static")

    def test_multiuse(self):
        self.formatter.format(
            FakeOp(self.FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['static', 'bootstrap'], use=['static']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6')))
        self.assertOut("* ", Color('fg', 'blue'), "app-arch/bzip2", "-1.0.3-r6", "::gentoo ",
            Color('fg', 'blue'), "{:0} ", Color('fg', 'yellow'), "[R] ",
            Color('fg', 'red'), "-bootstrap ", Color('fg', 'green'), "static")


class TestPortageFormatter(BaseFormatterTest, TestCase):

    formatterClass = PortageFormatter

    def setUp(self):
        pkg = FakeMutatedPkg('app-arch/bzip2-1.0.1-r1', slot='0')
        masked_atom = atom('>=app-arch/bzip2-2.0')
        self.domain_settings = {"ACCEPT_KEYWORDS": ("amd64",)}
        self.repo1 = FakeRepo(
            repo_id='gentoo', location='/var/gentoo/repos/gentoo',
            masks=(masked_atom,), domain_settings=self.domain_settings)
        self.repo2 = FakeRepo(
            repo_id='repo2', location='/var/gentoo/repos/repo2',
            domain_settings=self.domain_settings)
        self.vdb = FakeRepo(repo_id='vdb', pkgs=[pkg])
        BaseFormatterTest.setUp(self)

    def newFormatter(self, **kwargs):
        kwargs.setdefault('quiet_repo_display', False)
        kwargs.setdefault('installed_repos', self.vdb)
        return BaseFormatterTest.newFormatter(self, **kwargs)

    def repo_id(self, repo):
        if getattr(self.formatter, 'verbosity', 0):
            return '::' + repo.repo_id
        return ''

    def test_new(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.4')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), '     ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.4', Reset())

    def test_remove(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.4'), desc='remove'))
        self.assertOut('[', Color('fg', 'red'), 'uninstall', Reset(),
            '        ] ', Color('fg', 'red'), 'app-arch/bzip2-1.0.4', Reset())

    def test_upgrade(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.4'),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '     ', Color('fg', 'cyan'), Bold(), 'U', Reset(), '  ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.4', Reset(), ' ',
            Color('fg', 'blue'), Bold(), '[1.0.3-r6]', Reset())

    def test_downgrade(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6'),
            FakeMutatedPkg('app-arch/bzip2-1.0.4')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '     ', Color('fg', 'cyan'), Bold(), 'U', Reset(),
            Color('fg', 'blue'), Bold(), 'D' , Reset(), ' ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(), ' ',
            Color('fg', 'blue'), Bold(), '[1.0.4]', Reset())

    def test_reinstall(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', repo=self.repo1),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', repo=self.repo1)))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), f'app-arch/bzip2-1.0.3-r6{self.repo_id(self.repo1)}', Reset())

    def test_reinstall_from_new_repo(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', repo=self.repo1),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', repo=self.repo2)))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), f'app-arch/bzip2-1.0.3-r6{self.repo_id(self.repo1)}', Reset(),
            ' ', Color('fg', 'blue'), Bold(), f'[1.0.3-r6{self.repo_id(self.repo2)}]', Reset())

    def test_new_use(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['static'], use=['static'])))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), '     ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="', Color('fg', 'red'), Bold(), 'static', Reset(), '"')

    def test_new_nouse(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['static'])))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), '     ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="', Color('fg', 'blue'), Bold(), '-static', Reset(), '"')

    def test_nouse(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['static']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="', Color('fg', 'yellow'), Bold(), '-static', Reset(), '%"')

    def test_iuse_defaults(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', eapi='1', iuse=['+static', '-junk'], use=['static']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="', Color('fg', 'yellow'), Bold(), 'static', Reset(), "%* ",
            Color('fg', 'yellow'), Bold(), '-junk', Reset(), '%"')

    def test_use_enabled(self):
        self.formatter.format(FakeOp(
            FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['static'], use=['static']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', iuse=['static']),
        ))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="', Color('fg', 'green'), Bold(), 'static', Reset(), '*"')

    def test_use_disabled(self):
        self.formatter.format(FakeOp(
            FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['static']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', iuse=['static'], use=['static']),
        ))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="', Color('fg', 'green'), Bold(), '-static', Reset(), '*"')

    def test_multiuse(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['static', 'bootstrap'], use=['static']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="', Color('fg', 'yellow'), Bold(), 'static', Reset(), '%* ',
            Color('fg', 'yellow'), Bold(), '-bootstrap', Reset(), '%"')

    def test_misc(self):
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', slot='1')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), Color('fg', 'green'), Bold(),
            'S', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' ', Color('fg', 'blue'), Bold(), '[1.0.1-r1]', Reset())

    def test_fetch_restrict_no_fetchables(self):
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', restrict='fetch')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(),
            ' ', Color('fg', 'green'), Bold(), 'f', Reset(), '   ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset())

    # TODO
    def test_fetch_restrict_missing_fetchables(self):
        pass

    # TODO
    def test_fetch_restrict_prefetched_fetchables(self):
        pass

    def test_added_iuse_disabled(self):
        self.formatter.format(FakeOp(
            FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['bootstrap']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6'),
        ))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="', Color('fg', 'yellow'), Bold(), '-bootstrap', Reset(), '%"')

    def test_added_iuse_enabled(self):
        self.formatter.format(FakeOp(
            FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['static'], use=['static']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6'),
        ))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="', Color('fg', 'yellow'), Bold(), 'static', Reset(), '%*"')

    def test_dropped_iuse_disabled(self):
        self.formatter.format(FakeOp(
            FakeEbuildSrc('app-arch/bzip2-1.0.3-r6'),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', iuse=['bootstrap']),
        ))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset())

    def test_dropped_iuse_enabled(self):
        self.formatter.format(FakeOp(
            FakeEbuildSrc('app-arch/bzip2-1.0.3-r6'),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', iuse=['static'], use=['static']),
        ))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset())

    def test_use_expand(self):
        self.formatter = self.newFormatter(use_expand=set(["foo", "bar"]))
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6',
                iuse=['foo_static', 'foo_bootstrap', 'bar_baz'],
                use=['foo_static', 'bar_baz']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' BAR="', Color('fg', 'yellow'), Bold(), 'baz', Reset(), '%*"',
            ' FOO="', Color('fg', 'yellow'), Bold(), 'static', Reset(), '%* ',
            Color('fg', 'yellow'), Bold(), '-bootstrap', Reset(), '%"')

    def test_disabled_use(self):
        self.formatter.pkg_get_use = lambda pkg: (set(), set(), set(['static']))

        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['static', 'bootstrap'])))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), '     ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="',
            Color('fg', 'blue'), Bold(), '-bootstrap', Reset(), ' ',
            '(', Color('fg', 'blue'), Bold(), '-static', Reset(), ')"')

    def test_forced_use(self):
        self.formatter.pkg_get_use = lambda pkg: (set(['static']), set(), set())

        # new pkg: static use flag forced on
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['static'], use=['static'])))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), '     ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="(', Color('fg', 'red'), Bold(), 'static', Reset(), ')"')

        # rebuilt pkg: toggled static use flag forced on
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['static'], use=['static']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', iuse=['static'])))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="(', Color('fg', 'green'), Bold(), 'static', Reset(), '*)"')

        # rebuilt pkg: new static use flag forced on
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['static'], use=['static']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="(', Color('fg', 'yellow'), Bold(), 'static', Reset(), '%*)"')

    def test_forced_use_expand(self):
        self.formatter = self.newFormatter(use_expand=set(["ABI_X86", "TARGETS"]))
        self.formatter.pkg_get_use = lambda pkg: (set(['targets_X86']), set(), set())

        # rebuilt pkg: new abi_x86_64 and targets_X86 USE flags,
        # with abi_x86_64 disabled and targets_X86 forced on
        self.formatter.format(
            FakeOp(FakeEbuildSrc(
                'app-arch/bzip2-1.0.3-r6',
                iuse=['abi_x86_64', 'targets_X86'],
                use=['targets_X86']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' ABI_X86="', Color('fg', 'yellow'), Bold(), '-64', Reset(), '%"',
            ' TARGETS="(', Color('fg', 'yellow'), Bold(), 'X86', Reset(), '%*)"')

    def test_worldfile_atom(self):
        self.formatter.world_list = [atom('app-arch/bzip2')]
        self.formatter.format(
        FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6')))
        self.assertOut('[', Color('fg', 'green'), Bold(), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), '     ] ',
            Color('fg', 'green'), Bold(), 'app-arch/bzip2-1.0.3-r6', Reset())

class TestPortageVerboseFormatter(TestPortageFormatter):

    def newFormatter(self, **kwargs):
        kwargs.setdefault("verbosity", 1)
        kwargs.setdefault("unstable_arch", "~amd64")
        return TestPortageFormatter.newFormatter(self, **kwargs)

    def test_install_symbol_unkeyworded(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', repo=self.repo1, keywords=())))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), '    ',
            Color('fg', 'red'), Bold(), '*', Reset(), '] ',
            Color('fg', 'green'), f'app-arch/bzip2-1.0.3-r6{self.repo_id(self.repo1)}', Reset())

    def test_install_symbol_unstable(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', repo=self.repo1, keywords=('~amd64',))))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), '    ',
            Color('fg', 'yellow'), Bold(), '~', Reset(), '] ',
            Color('fg', 'green'), f'app-arch/bzip2-1.0.3-r6{self.repo_id(self.repo1)}', Reset())

    def test_install_symbol_masked(self):
        self.formatter.format(
           FakeOp(FakeEbuildSrc('app-arch/bzip2-2.1', repo=self.repo1)))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
           '  ', Color('fg', 'green'), Bold(), 'N', Reset(), '    ',
           Color('fg', 'red'), Bold(), '#', Reset(), '] ',
           Color('fg', 'green'), f'app-arch/bzip2-2.1{self.repo_id(self.repo1)}', Reset())

    def test_repo_id(self):
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', repo=self.repo1)))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), '     ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6::gentoo', Reset())
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', repo=self.repo2)))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), '     ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6::repo2', Reset())
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.4', repo=self.repo1),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', repo=self.repo1)))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '     ', Color('fg', 'cyan'), Bold(), 'U', Reset(), '  ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.4::gentoo', Reset(), ' ',
            Color('fg', 'blue'), Bold(), '[1.0.3-r6::gentoo]', Reset())
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.4', repo=self.repo2),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', repo=self.repo1)))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '     ', Color('fg', 'cyan'), Bold(), 'U', Reset(), '  ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.4::repo2', Reset(), ' ',
            Color('fg', 'blue'), Bold(), '[1.0.3-r6::gentoo]', Reset())
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.4', repo=self.repo1),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', repo=self.repo2)))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '     ', Color('fg', 'cyan'), Bold(), 'U', Reset(), '  ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.4::gentoo', Reset(), ' ',
            Color('fg', 'blue'), Bold(), '[1.0.3-r6::repo2]', Reset())
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.4', repo=self.repo2),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', repo=self.repo2)))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '     ', Color('fg', 'cyan'), Bold(), 'U', Reset(), '  ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.4::repo2', Reset(), ' ',
            Color('fg', 'blue'), Bold(), '[1.0.3-r6::repo2]', Reset())

    def test_misc(self):
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', slot='0')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), '     ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset())
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', slot='0', subslot='0')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), '     ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset())
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', slot='0', subslot='2')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), '     ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6:0/2', Reset())
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', slot='foo')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), Color('fg', 'green'), Bold(),
            'S', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6:foo', Reset(),
            ' ', Color('fg', 'blue'), Bold(), '[1.0.1-r1:0]', Reset())
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', slot='1', subslot='0')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), Color('fg', 'green'), Bold(),
            'S', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6:1/0', Reset(),
            ' ', Color('fg', 'blue'), Bold(), '[1.0.1-r1:0]', Reset())
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', slot='2', subslot='foo')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), Color('fg', 'green'), Bold(),
            'S', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6:2/foo', Reset(),
            ' ', Color('fg', 'blue'), Bold(), '[1.0.1-r1:0]', Reset())

    def test_dropped_iuse_disabled(self):
        self.formatter.format(FakeOp(
            FakeEbuildSrc('app-arch/bzip2-1.0.3-r6'),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', iuse=['bootstrap']),
        ))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="(', Color('fg', 'yellow'), Bold(), '-bootstrap', Reset(), '%)"')

    def test_dropped_iuse_enabled(self):
        self.formatter.format(FakeOp(
            FakeEbuildSrc('app-arch/bzip2-1.0.3-r6'),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', iuse=['static'], use=['static']),
        ))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="(', Color('fg', 'yellow'), Bold(), '-static', Reset(), '%*)"')

    def test_changed_use(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6',
                iuse=['static', 'bootstrap', 'perl', 'foobar', 'rice'],
                use=['static', 'rice']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6',
                iuse=['bootstrap', 'foobar', 'rice', 'kazaam'],
                use=['foobar'])))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(), ' USE="',
            Color('fg', 'green'), Bold(), 'rice', Reset(), '* ',
            Color('fg', 'yellow'), Bold(), 'static', Reset(), '%* ',
            Color('fg', 'blue'), Bold(), '-bootstrap', Reset(), ' ',
            Color('fg', 'green'), Bold(), '-foobar', Reset(), '* ',
            Color('fg', 'yellow'), Bold(), '-perl', Reset(), '% ',
            '(', Color('fg', 'yellow'), Bold(), '-kazaam', Reset(), '%)"')

    def test_forced_use_verbose(self):
        self.formatter.pkg_get_use = lambda pkg: (set(['static']), set(), set())

        # rebuilt pkg: unchanged static use flag forced on
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['static'], use=['static']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', iuse=['static'], use=['static'])))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="(', Color('fg', 'red'), Bold(), 'static', Reset(), ')"')

    def test_removed_use(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['static'], use=['static']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', iuse=['static', 'bootstrap', 'foo'], use=['static', 'foo'])))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="', Color('fg', 'red'), Bold(), 'static', Reset(), ' ',
            '(', Color('fg', 'yellow'), Bold(), '-bootstrap', Reset(), '%) ',
            '(', Color('fg', 'yellow'), Bold(), '-foo', Reset(), '%*)"')

    def test_end(self):
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', repo=self.repo1)))
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', repo=self.repo2)))
        self.fakeout.resetstream()
        self.formatter.end()
        self.assertOut('\nTotal: 2 packages (2 new)\n\n',
            suffix=[''])

class TestPortageVerboseRepoIdFormatter(TestPortageVerboseFormatter):
    suffix = [Color("fg", "cyan"), ' [1]\n']

    def setUp(self):
        TestPortageVerboseFormatter.setUp(self)
        self.repo3 = FakeRepo(
            location='/var/gentoo/repos/repo3', domain_settings=self.domain_settings)

    def newFormatter(self, **kwargs):
        kwargs.setdefault("quiet_repo_display", True)
        return TestPortageVerboseFormatter.newFormatter(self, **kwargs)

    def repo_id(self, repo):
        return ''

    def test_repo_id(self):
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', repo=self.repo1)))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), '     ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset())

    def test_end(self):
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', repo=self.repo1)))
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', repo=self.repo2)))
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', repo=self.repo3)))
        self.fakeout.resetstream()
        self.formatter.end()
        self.assertOut('\nTotal: 3 packages (3 new)\n\n',
            ' ', Color('fg', 'cyan'), '[1]', Reset(),' gentoo (/var/gentoo/repos/gentoo)\n',
            ' ', Color('fg', 'cyan'), '[2]', Reset(),' repo2 (/var/gentoo/repos/repo2)\n',
            ' ', Color('fg', 'cyan'), '[3]', Reset(),' /var/gentoo/repos/repo3\n',
            suffix=[''])
