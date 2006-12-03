# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.test import TestCase
from pkgcore.ebuild import atom, errors
from pkgcore.ebuild.cpv import CPV


class FakePkg(CPV):
    __slots__ = ("__dict__")
    def __init__(self, cpv, use=(), slot=0):
        CPV.__init__(self, cpv)
        object.__setattr__(self, "use", use)
        object.__setattr__(self, "slot", str(slot))


class Test_native_atom(TestCase):

    class kls(atom.atom):
        locals().update(atom.native_atom_overrides.iteritems())
    kls = staticmethod(kls)

    def test_glob(self):
        self.assertRaises(errors.MalformedAtom, self.kls,
            "dev-util/diffball-1*")
        self.assertRaises(errors.MalformedAtom, self.kls,
            "dev-util/diffball-1.*")

        a = self.kls("=dev-util/diffball-1.2*")
        self.assertTrue(a.match(CPV("dev-util/diffball-1.2")))
        self.assertTrue(a.match(CPV("dev-util/diffball-1.2.0")))
        self.assertTrue(a.match(CPV("dev-util/diffball-1.2-r1")))
        self.assertTrue(a.match(CPV("dev-util/diffball-1.2_alpha")))
        self.assertFalse(a.match(CPV("dev-util/diffball-1")))

    def test_nonversioned(self):
        a = self.kls("kde-base/kde")
        self.assertTrue(a.match(CPV("kde-base/kde")))
        self.assertFalse(a.match(CPV("kde-base/kde2")))
        self.assertTrue(a.match(CPV("kde-base/kde-3")))
    
    def make_atom(self, s, ops, ver):
        l = []
        if -1 in ops:
            l.append(">")
        if 0 in ops:
            l.append("=")
        if 1 in ops:
            l.append("<")
        return self.kls("%s%s-%s" % (''.join(l), s, ver))
    
    def test_versioned(self):
        as = "app-arch/tarsync"
        le_cpv = CPV("%s-0" % as)
        eq_cpv = CPV("%s-1.1-r2" % as)
        ge_cpv = CPV("%s-2" % as)
        # <, =, >
        ops = (-1, 0, 1)
        
        for ops, ver in ((-1, "1.0"), (-1, "1.1"),
            (0, "1.1-r2"), (1, "1.1-r3"), (1, "1.2")):
            if not isinstance(ops, (list, tuple)):
                ops = (ops,)
            a = self.make_atom(as, ops, ver)
            if -1 in ops:
                self.assertTrue(a.match(ge_cpv))
                self.assertTrue(a.match(eq_cpv))
                self.assertFalse(a.match(le_cpv))
            if 0 in ops:
                self.assertTrue(a.match(eq_cpv))
                if ops == (0,):
                    self.assertFalse(a.match(le_cpv))
                    self.assertFalse(a.match(ge_cpv))
            if 1 in ops:
                self.assertFalse(a.match(ge_cpv))
                self.assertTrue(a.match(eq_cpv))
                self.assertTrue(a.match(le_cpv))

    def test_norev(self):
        as = "app-arch/tarsync"
        a = self.kls("~%s-1" % as)
        self.assertTrue(a.match(CPV("%s-1" % as)))
        self.assertTrue(a.match(CPV("%s-1-r1" % as)))
        self.assertFalse(a.match(CPV("%s-2" % as)))


    def test_use(self):
        as = "dev-util/bsdiff"
        c = FakePkg(as, ("debug",))
        self.assertTrue(self.kls("%s[debug]" % as).match(c))
        self.assertFalse(self.kls("%s[-debug]" % as).match(c))
        self.assertTrue(self.kls("%s[debug,-not]" % as).match(c))
        self.assertRaises(errors.MalformedAtom, self.kls, "%s[]" % as)

    def test_slot(self):
        as = "dev-util/confcache"
        c = FakePkg(as, (), 1)
        self.assertFalse(self.kls("%s:0" % as).match(c))
        self.assertTrue(self.kls("%s:1" % as).match(c))
        self.assertFalse(self.kls("%s:2" % as).match(c))
        self.assertTrue(self.kls("%s:0,1" % as).match(c))
        self.assertFalse(self.kls("%s:0,2" % as).match(c))
        # shouldn't puke, but has, thus checking"
        self.kls("sys-libs/db:4.4")
        self.assertRaises(errors.MalformedAtom, self.kls, "dev-util/foo:")
        self.assertRaises(errors.MalformedAtom, self.kls, "dev-util/foo:1,,0")

    def test_invalid_atom(self):
        self.assertRaises(errors.MalformedAtom, self.kls, '~dev-util/spork')
        self.assertRaises(errors.MalformedAtom, self.kls, '>dev-util/spork')
        self.assertRaises(errors.MalformedAtom, self.kls, 'dev-util/spork-3')
        self.assertRaises(errors.MalformedAtom, self.kls, 'spork')

    def test_intersects(self):
        for this, that, result in [
            ('cat/pkg', 'pkg/cat', False),
            ('cat/pkg', 'cat/pkg', True),
            ('cat/pkg:1', 'cat/pkg:1', True),
            ('cat/pkg:1', 'cat/pkg:2', False),
            ('cat/pkg:1', 'cat/pkg[foo]', True),
            ('cat/pkg[foo]', 'cat/pkg[-bar]', True),
            ('cat/pkg[foo]', 'cat/pkg[-foo]', False),
            ('>cat/pkg-3', '>cat/pkg-1', True),
            ('>cat/pkg-3', '<cat/pkg-3', False),
            ('>=cat/pkg-3', '<cat/pkg-3', False),
            ('>cat/pkg-2', '=cat/pkg-2*', True),
            ('<cat/pkg-2_alpha1', '=cat/pkg-2*', True),
            ('=cat/pkg-2', '=cat/pkg-2', True),
            ('=cat/pkg-2*', '=cat/pkg-2.3*', True),
            ('>cat/pkg-2.4', '=cat/pkg-2*', True),
            ('<cat/pkg-2.4', '=cat/pkg-2*', True),
            ('<cat/pkg-1', '=cat/pkg-2*', False),
            ('~cat/pkg-2', '>cat/pkg-2-r1', True),
            ('~cat/pkg-2', '<cat/pkg-2', False),
            ('=cat/pkg-1-r1*', '<cat/pkg-1-r1', False),
            ('=cat/pkg-1*', '>cat/pkg-2', False),
            ('>=cat/pkg-8.4', '=cat/pkg-8.3.4*', False),
            ]:
            this_atom = self.kls(this)
            that_atom = self.kls(that)
            self.assertEquals(
                result, this_atom.intersects(that_atom),
                '%s intersecting %s should be %s' % (this, that, result))
            self.assertEquals(
                result, that_atom.intersects(this_atom),
                '%s intersecting %s should be %s' % (that, this, result))

    def test_comparison(self):
        self.assertEquals(self.kls('cat/pkg'), self.kls('cat/pkg'))
        self.assertEquals(self.kls('=cat/pkg-0'), self.kls('=cat/pkg-0'))
        self.assertNotEquals(self.kls('cat/pkg:1'), self.kls('cat/pkg'))
        self.assertNotEquals(self.kls('cat/pkg[foo]'), self.kls('cat/pkg'))
        self.assertNotEquals(self.kls('cat/pkg[foo]'),
                             self.kls('cat/pkg[-foo]'))
        self.assertEquals(self.kls('cat/pkg[foo,-bar]'),
                          self.kls('cat/pkg[-bar,foo]'))
        self.assertNotEquals(self.kls('cat/pkg'), self.kls('!cat/pkg'))
        self.assertNotEquals(self.kls('<cat/pkg-2'), self.kls('>cat/pkg-2'))
        self.assertNotEquals(self.kls('=cat/pkg-2*'), self.kls('=cat/pkg-2'))

    def test_compatibility(self):
        self.assertFalse(self.kls('=dev-util/diffball-0.7').match(
            FakePkg('dev-util/diffball-0.7.0')))
        # see bug http://bugs.gentoo.org/152127
        self.assertFalse(self.kls('>=sys-apps/portage-2.1.0_pre3-r5').match(
            FakePkg('sys-apps/portage-2.1_pre3-r5')))


class Test_cpy_atom(Test_native_atom):
    
    kls = staticmethod(atom.atom)
    if atom.atom_overrides is atom.native_atom_overrides:
        skip = "extension isn't available"
