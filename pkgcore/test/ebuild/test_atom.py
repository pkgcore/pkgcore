# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.test import TestCase
from pkgcore.ebuild import atom
from pkgcore.ebuild.cpv import CPV

class FakePkg(CPV):
    __slots__ = ("__dict__")
    def __init__(self, cpv, use=(), slot=0):
        CPV.__init__(self, cpv)
        object.__setattr__(self, "use", use)
        object.__setattr__(self, "slot", str(slot))

class TestAtom(TestCase):

    def test_glob(self):
        self.assertRaises(atom.MalformedAtom, atom.atom, "dev-util/diffball-1*")
        self.assertRaises(atom.MalformedAtom, atom.atom, "dev-util/diffball-1.*")

        a = atom.atom("=dev-util/diffball-1.2*")
        self.assertEqual(a.glob, True)
        self.assertTrue(a.match(CPV("dev-util/diffball-1.2")))
        self.assertTrue(a.match(CPV("dev-util/diffball-1.2.0")))
        self.assertTrue(a.match(CPV("dev-util/diffball-1.2-r1")))
        self.assertTrue(a.match(CPV("dev-util/diffball-1.2_alpha")))
        self.assertFalse(a.match(CPV("dev-util/diffball-1")))

    def test_nonversioned(self):
        a = atom.atom("kde-base/kde")
        self.assertTrue(a.match(CPV("kde-base/kde")))
        self.assertFalse(a.match(CPV("kde-base/kde2")))
        self.assertTrue(a.match(CPV("kde-base/kde-3")))
    
    @staticmethod
    def make_atom(s, ops, ver):
        l = []
        if -1 in ops:
            l.append(">")
        if 0 in ops:
            l.append("=")
        if 1 in ops:
            l.append("<")
        return atom.atom("%s%s-%s" % (''.join(l), s, ver))
    
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
        a = atom.atom("~%s-1" % as)
        self.assertTrue(a.match(CPV("%s-1" % as)))
        self.assertTrue(a.match(CPV("%s-1-r1" % as)))
        self.assertFalse(a.match(CPV("%s-2" % as)))


    def test_use(self):
        as = "dev-util/bsdiff"
        c = FakePkg(as, ("debug",))
        self.assertTrue(atom.atom("%s[debug]" % as).match(c))
        self.assertFalse(atom.atom("%s[-debug]" % as).match(c))
        self.assertTrue(atom.atom("%s[debug,-not]" % as).match(c))
        self.assertTrue(atom.atom("%s[debug, -not]" % as).match(c))
        self.assertRaises(atom.MalformedAtom, atom.atom, "%s[]" % as)

    def test_slot(self):
        as = "dev-util/confcache"
        c = FakePkg(as, (), 1)
        self.assertFalse(atom.atom("%s:0" % as).match(c))
        self.assertTrue(atom.atom("%s:1" % as).match(c))
        self.assertFalse(atom.atom("%s:2" % as).match(c))
        # shouldn't puke, but has, thus checking"
        atom.atom("sys-libs/db:4.4")
        self.assertRaises(atom.MalformedAtom, atom.atom, "dev-util/foo:")

    def test_invalid_ops(self):
        self.assertRaises(atom.MalformedAtom, atom.atom, '~dev-util/spork')
        self.assertRaises(atom.MalformedAtom, atom.atom, '>dev-util/spork')
        self.assertRaises(atom.MalformedAtom, atom.atom, 'dev-util/spork-3')
