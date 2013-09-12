# Copyright 2007 Charlie Shepherd <masterdriverz@gmail.com>
# License: GPL2

import difflib, sys

from snakeoil.compatibility import force_bytes
from pkgcore.test import TestCase
from pkgcore.ebuild.formatter import (BasicFormatter, PkgcoreFormatter,
    PortageFormatter, PaludisFormatter)
from pkgcore.test.misc import FakePkg, FakeRepo
from pkgcore.test.scripts.helpers import FakeStreamFormatter, Color, Reset, Bold
from pkgcore.ebuild.misc import collapsed_restrict_to_data

if sys.version_info < (2, 6):
    bytes = str

# b''.join but works on python < 2.6
_join_bytes = force_bytes('').join

# These two are probably unnecessary with ferringb's changes to
# PkgcoreFormatter, but as he's the one that uses it there's no point fixing
# what ain't broke. --charlie
class FakeMutatedPkg(FakePkg):
    def __str__(self):
        # Yes this should be less hackish (and hardcoded values suck),
        # but we can't really subclass MutatedPkg so this will have to do
        return "MutatedPkg(built ebuild: %s, overrides=('depends', 'rdepends'))" % self.cpvstr

class FakeEbuildSrc(FakePkg):
    def __str__(self):
        # Yes this should be less hackish (and hardcoded values suck)
        # but we can't really subclass ebuild_src so this will have to do
        return "config wrapped(use): ebuild src: %s" % self.cpvstr


class FakeOp(object):
    def __init__(self, package, oldpackage=None, desc='add'):
        self.pkg = package
        if oldpackage:
            self.old_pkg = oldpackage
            self.desc = 'replace'
        else:
            self.desc = desc

class BaseFormatterTest(object):
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
                except Exception, e:
                    self.assertEqual(autoline, self.fakeout.autoline, msg=
                        "exception thrown %s, autoline was %s, now is %s" % (e, autoline, self.fakeout.autoline))
                    raise
                self.assertEqual(autoline, self.fakeout.autoline, msg=
                    "autoline was %s, now is %s" % (autoline, self.fakeout.autoline))
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
            if isinstance(arg, unicode):
                stringlist.append(arg.encode('ascii'))
            elif isinstance(arg, bytes):
                stringlist.append(arg)
            else:
                objectlist.append(_join_bytes(stringlist))
                stringlist = []
                objectlist.append(arg)
        objectlist.append(_join_bytes(stringlist))

        # Hack because a list with an empty string in is True
        if objectlist == [force_bytes('')]:
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
    def test_op(self):
        # Make sure we ignore versions...
        self.formatter.format(FakeOp(FakeMutatedPkg('dev-util/diffball-1.1')))
        self.assertOut('dev-util/diffball')

class TestPkgcoreFormatter(BaseFormatterTest, TestCase):
    formatterClass = PkgcoreFormatter
    def test_op(self):
        # This basically just tests string methods
        self.formatter.format(
            FakeOp(FakeEbuildSrc('dev-util/diffball-1.2'),
                FakeMutatedPkg('dev-util/diffball-1.1')))
        self.assertOut(
            "replace dev-util/diffball-1.1, "
            "dev-util/diffball-1.2")

        self.formatter.format(FakeOp(FakeEbuildSrc('dev-util/diffball-1.0')))
        self.assertOut("add     dev-util/diffball-1.0")

        self.formatter.format(FakeOp(FakeEbuildSrc('dev-util/diffball-1.0',
            repo=FakeRepo(repo_id='gentoo', location='/usr/portage'))))
        self.assertOut("add     dev-util/diffball-1.0::gentoo")

        self.formatter.format(
            FakeOp(FakeEbuildSrc('dev-util/diffball-1.2',
                   repo=FakeRepo(repo_id='gentoo', location='/usr/portage')),
                FakeMutatedPkg('dev-util/diffball-1.1')))
        self.assertOut(
            "replace dev-util/diffball-1.1, "
            "dev-util/diffball-1.2::gentoo")


class CountingFormatterTest(BaseFormatterTest):

    endprefix = ""
    endsuffix = "\n"

    def newFormatter(self, **kwargs):
        kwargs.setdefault('verbose', True)
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


class TestPaludisFormatter(CountingFormatterTest, TestCase):
    formatterClass = PaludisFormatter

    def setUp(self):
        BaseFormatterTest.setUp(self)
        self.repo = FakeRepo(repo_id='gentoo', location='/usr/portage')

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

    def test_iuse_filter(self):
        self.formatter.format(
            FakeOp(self.FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['+static', '-junk'], use=['static']),
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
        self.livefs = FakeRepo(repo_id='vdb', pkgs=[pkg])
        BaseFormatterTest.setUp(self)

    def newFormatter(self, **kwargs):
        kwargs.setdefault('quiet_repo_display', False)
        kwargs.setdefault('livefs_repos', self.livefs)
        return BaseFormatterTest.newFormatter(self, **kwargs)

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
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6'),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset())

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

    def test_iuse_filter(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['+static', '-junk'], use=['static']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="', Color('fg', 'yellow'), Bold(), 'static', Reset(), "%* ",
            Color('fg', 'yellow'), Bold(), '-junk', Reset(), '%"')

    def test_use(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['static'], use=['static']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="', Color('fg', 'yellow'), Bold(), 'static', Reset(), '%*"')

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

        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', restrict='fetch')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(),
            ' ', Color('fg', 'red'), Bold(), 'F', Reset(), '   ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset())

    def test_changed_use(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['static', 'bootstrap'], use=['static']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', iuse=['static'], use=['static'])))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="', Color('fg', 'yellow'), Bold(), '-bootstrap', Reset(), '%"')
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
            Color('fg', 'yellow'), Bold(), '-foobar', Reset(), '* ',
            Color('fg', 'yellow'), Bold(), '-perl', Reset(), '%"')

    def test_use_expand(self):
        self.formatter = self.newFormatter(use_expand=set(["foo"]))
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6',
                iuse=['foo_static', 'foo_bootstrap'], use=['foo_static']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6')))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' FOO="', Color('fg', 'yellow'), Bold(), 'static', Reset(), '%* ',
            Color('fg', 'yellow'), Bold(), '-bootstrap', Reset(), '%"')

    def test_disabled_use(self):
        from pkgcore.ebuild.atom import atom
        self.formatter.disabled_use = collapsed_restrict_to_data(([(atom('=app-arch/bzip2-1.0.3-r6'),('static'))]))
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['static', 'bootstrap'])))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), '     ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="',
            Color('fg', 'blue'), Bold(), '-bootstrap', Reset(), ' ',
            '(', Color('fg', 'blue'), Bold(), '-static', Reset(), ')"')

    def test_worldfile_atom(self):
        from pkgcore.ebuild.atom import atom
        self.formatter.world_list = [atom('app-arch/bzip2')]
        self.formatter.format(
        FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6')))
        self.assertOut('[', Color('fg', 'green'), Bold(), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), '     ] ',
            Color('fg', 'green'), Bold(), 'app-arch/bzip2-1.0.3-r6', Reset())

class TestPortageVerboseFormatter(TestPortageFormatter):

    def newFormatter(self, **kwargs):
        kwargs.setdefault("verbose", True)
        return TestPortageFormatter.newFormatter(self, **kwargs)

    def setUp(self):
        TestPortageFormatter.setUp(self)
        self.repo1 = FakeRepo(repo_id='gentoo', location='/usr/portage')
        self.repo2 = FakeRepo(location='/usr/local/portage')
        self.repo3 = FakeRepo(repo_id='fakerepo', location='/var/cache/gentoo/repos/fakerepo')

    def test_repo_id(self):
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', repo=self.repo1)))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), '     ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset())
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', repo=self.repo3)))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), '     ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6::fakerepo', Reset())
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.4', repo=self.repo1),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', repo=self.repo1)))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '     ', Color('fg', 'cyan'), Bold(), 'U', Reset(), '  ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.4', Reset(), ' ',
            Color('fg', 'blue'), Bold(), '[1.0.3-r6]', Reset())
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.4', repo=self.repo3),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', repo=self.repo1)))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '     ', Color('fg', 'cyan'), Bold(), 'U', Reset(), '  ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.4::fakerepo', Reset(), ' ',
            Color('fg', 'blue'), Bold(), '[1.0.3-r6::gentoo]', Reset())
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.4', repo=self.repo1),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', repo=self.repo3)))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '     ', Color('fg', 'cyan'), Bold(), 'U', Reset(), '  ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.4::gentoo', Reset(), ' ',
            Color('fg', 'blue'), Bold(), '[1.0.3-r6::fakerepo]', Reset())
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.4', repo=self.repo3),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', repo=self.repo3)))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '     ', Color('fg', 'cyan'), Bold(), 'U', Reset(), '  ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.4::fakerepo', Reset(), ' ',
            Color('fg', 'blue'), Bold(), '[1.0.3-r6::fakerepo]', Reset())

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

    def test_changed_use(self):
        self.formatter.format(
            FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', iuse=['static', 'bootstrap'], use=['static']),
            FakeMutatedPkg('app-arch/bzip2-1.0.3-r6', iuse=['static'], use=['static'])))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '   ', Color('fg', 'yellow'), Bold(), 'R', Reset(), '    ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset(),
            ' USE="', Color('fg', 'red'), Bold(), 'static', Reset(), ' ',
            Color('fg', 'yellow'), Bold(), '-bootstrap', Reset(), '%"')
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
            Color('fg', 'yellow'), Bold(), '-foobar', Reset(), '* ',
            Color('fg', 'yellow'), Bold(), '-perl', Reset(), '%"')

    def test_end(self):
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', repo=self.repo1)))
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', repo=self.repo2)))
        self.fakeout.resetstream()
        self.formatter.end()
        self.assertOut('\nTotal: 2 packages (2 new)\n\n',
            suffix=[''])

class TestPortageVerboseRepoIdFormatter(TestPortageVerboseFormatter):
    suffix = [Color("fg", "cyan"), ' [1]\n']

    def newFormatter(self, **kwargs):
        kwargs.setdefault("quiet_repo_display", True)
        return TestPortageVerboseFormatter.newFormatter(self, **kwargs)

    def test_repo_id(self):
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', repo=self.repo1)))
        self.assertOut('[', Color('fg', 'green'), 'ebuild', Reset(),
            '  ', Color('fg', 'green'), Bold(), 'N', Reset(), '     ] ',
            Color('fg', 'green'), 'app-arch/bzip2-1.0.3-r6', Reset())

    def test_end(self):
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', repo=self.repo1)))
        self.formatter.format(FakeOp(FakeEbuildSrc('app-arch/bzip2-1.0.3-r6', repo=self.repo2)))
        self.fakeout.resetstream()
        self.formatter.end()
        self.assertOut('\nTotal: 2 packages (2 new)\n\n',
            ' ', Color('fg', 'cyan'), '[1]', Reset(),' gentoo (/usr/portage)\n',
            ' ', Color('fg', 'cyan'), '[2]', Reset(),' /usr/local/portage\n',
            suffix=[''])
