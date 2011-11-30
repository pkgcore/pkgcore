# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# Copyright: 2007 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

import os
from snakeoil.test import mixins
from pkgcore.test import silence_logging
from snakeoil import osutils
pjoin = osutils.pjoin
from pkgcore.ebuild import repository
from pkgcore.ebuild.atom import atom
from pkgcore.repository import errors
from pkgcore.ebuild import errors as ebuild_errors

class UnconfiguredTreeTest(mixins.TempDirMixin):

    def mk_tree(self, path, *args, **kwds):
        return repository._UnconfiguredTree(path, *args, **kwds)

    def setUp(self):
        mixins.TempDirMixin.setUp(self)
        self.pdir = pjoin(self.dir, 'profiles')
        osutils.ensure_dirs(self.pdir)

    def test_basics(self):
        self.assertRaises(
            errors.InitializationError,
            self.mk_tree, pjoin(self.dir, 'missing'))
        open(pjoin(self.dir, 'random'), 'w').write('random')
        self.assertRaises(
            errors.InitializationError,
            self.mk_tree, pjoin(self.dir, 'random'))

        repo = self.mk_tree(self.dir)
        # Just make sure these do not raise.
        self.assertTrue(str(repo))
        self.assertTrue(repr(repo))

    def test_thirdpartymirrors(self):
        open(pjoin(self.pdir, 'thirdpartymirrors'), 'w').write('''\
spork		http://sporks/ http://moresporks/
foon		foon://foons/
''')
        mirrors = self.mk_tree(self.dir).mirrors
        self.assertEqual(['foon', 'spork'], sorted(mirrors))
        self.assertEqual(
            ['http://moresporks/', 'http://sporks/'],
            sorted(mirrors['spork']))
        open(pjoin(self.pdir, 'thirdpartymirrors'), 'w').write(
            "foon  dar\n")
        self.assertEqual(self.mk_tree(self.dir).mirrors.keys(),
            ['foon'])

    @silence_logging
    def test_repo_id(self):
        dir1 = pjoin(self.dir, '1')
        os.mkdir(dir1, 0755)
        repo = self.mk_tree(dir1)
        self.assertEqual(repo.repo_id, '<unlabeled repository %s>' % (dir1,))
        dir2 = pjoin(self.dir, '2')
        osutils.ensure_dirs(pjoin(dir2, 'profiles'))
        open(pjoin(dir2, 'profiles', 'repo_name'), 'w').write('testrepo\n')
        repo = self.mk_tree(dir2)
        self.assertEqual('testrepo', repo.repo_id)

    def test_categories_packages(self):
        osutils.ensure_dirs(pjoin(self.dir, 'cat', 'pkg'))
        osutils.ensure_dirs(pjoin(self.dir, 'empty', 'empty'))
        osutils.ensure_dirs(pjoin(self.dir, 'scripts', 'pkg'))
        osutils.ensure_dirs(pjoin(self.dir, 'notcat', 'CVS'))
        # "touch"
        open(pjoin(self.dir, 'cat', 'pkg', 'pkg-3.ebuild'), 'w')
        repo = self.mk_tree(self.dir)
        self.assertEqual(
            {'cat': (), 'notcat': (), 'empty': ()}, dict(repo.categories))
        self.assertEqual(
            {'cat': ('pkg',), 'empty': ('empty',), 'notcat': ()},
            dict(repo.packages))
        self.assertEqual(
            {('cat', 'pkg'): ('3',), ('empty', 'empty'): ()},
            dict(repo.versions))

        for x in ("1-scm", "scm", "1-try", "1_beta-scm", "1_beta-try"):
            for rev in ("", "-r1"):
                fp = pjoin(self.dir, 'cat', 'pkg', 'pkg-%s%s.ebuild' %
                    (x, rev))
                open(fp, 'w')
                repo = self.mk_tree(self.dir)
                self.assertRaises(ebuild_errors.InvalidCPV,
                    repo.match, atom('cat/pkg'))
                repo = self.mk_tree(self.dir, ignore_paludis_versioning=True)
                self.assertEqual(sorted(x.cpvstr for x in
                    repo.itermatch(atom('cat/pkg'))), ['cat/pkg-3'])
                os.unlink(fp)

    def test_package_mask(self):
        open(pjoin(self.pdir, 'package.mask'), 'w').write('''\
# lalala
it-is/broken
<just/newer-than-42
''')
        repo = self.mk_tree(self.dir)
        self.assertEqual(sorted([atom('it-is/broken'),
            atom('<just/newer-than-42')]),
            sorted(repo.default_visibility_limiters))
