# Copyright: 2007 Marien Zwart <marienz@gentoo.org>
# License: GPL2


from pkgcore.test import mixins
from pkgcore.util import osutils
from pkgcore.ebuild import repository
from pkgcore.ebuild.atom import atom
from pkgcore.repository import errors


class UnconfiguredTreeTest(mixins.TempDirMixin):

    def setUp(self):
        mixins.TempDirMixin.setUp(self)
        self.pdir = osutils.pjoin(self.dir, 'profiles')
        osutils.ensure_dirs(self.pdir)

    def test_basics(self):
        self.assertRaises(
            errors.InitializationError,
            repository.UnconfiguredTree, osutils.pjoin(self.dir, 'missing'))
        open(osutils.pjoin(self.dir, 'random'), 'w').write('random')
        self.assertRaises(
            errors.InitializationError,
            repository.UnconfiguredTree, osutils.pjoin(self.dir, 'random'))

        repo = repository.UnconfiguredTree(self.dir)
        # Just make sure these do not raise.
        self.assertTrue(str(repo))
        self.assertTrue(repr(repo))

    def test_thirdpartymirrors(self):
        open(osutils.pjoin(self.pdir, 'thirdpartymirrors'), 'w').write('''\
spork		http://sporks/ http://moresporks/
foon		foon://foons/
''')
        mirrors = repository.UnconfiguredTree(self.dir).mirrors
        self.assertEqual(['foon', 'spork'], sorted(mirrors))
        self.assertEqual(
            ['http://moresporks/', 'http://sporks/'],
            sorted(mirrors['spork']))

    def test_repo_id(self):
        repo = repository.UnconfiguredTree(self.dir)
        self.assertEqual(self.dir, repo.repo_id)
        open(osutils.pjoin(self.pdir, 'repo_name'), 'w').write('testrepo\n')
        repo = repository.UnconfiguredTree(self.dir)
        self.assertEqual('testrepo', repo.repo_id)

    def test_categories_packages(self):
        osutils.ensure_dirs(osutils.pjoin(self.dir, 'cat', 'pkg'))
        osutils.ensure_dirs(osutils.pjoin(self.dir, 'empty', 'empty'))
        osutils.ensure_dirs(osutils.pjoin(self.dir, 'scripts', 'pkg'))
        osutils.ensure_dirs(osutils.pjoin(self.dir, 'notcat', 'CVS'))
        # "touch"
        open(osutils.pjoin(self.dir, 'cat', 'pkg', 'pkg-3.ebuild'), 'w')
        repo = repository.UnconfiguredTree(self.dir)
        self.assertEqual(
            {'cat': (), 'notcat': (), 'empty': ()}, dict(repo.categories))
        self.assertEqual(
            {'cat': ('pkg',), 'empty': ('empty',), 'notcat': ()},
            dict(repo.packages))
        self.assertEqual(
            {('cat', 'pkg'): ('3',), ('empty', 'empty'): ()},
            dict(repo.versions))

    def test_package_mask(self):
        open(osutils.pjoin(self.pdir, 'package.mask'), 'w').write('''\
# lalala
it-is/broken
<just/newer-than-42
''')
        repo = repository.UnconfiguredTree(self.dir)
        self.assertEqual(sorted([atom('it-is/broken'),
            atom('<just/newer-than-42')]),
            sorted(repo.default_visibility_limiters))
