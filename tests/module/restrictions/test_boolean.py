from snakeoil.test import TestCase

from pkgcore.restrictions import boolean, restriction

true = restriction.AlwaysBool(node_type='foo', negate=True)
false = restriction.AlwaysBool(node_type='foo', negate=False)


class AlwaysForcableBool(boolean.base):

    __slots__ = ()

    def force_True(self, action, *args):
        yield True

    match = force_False = force_True


class base:

    kls = None

    def test_invalid_restrictions(self):
        self.assertRaises(TypeError, self.kls, 42, node_type='foo')
        base = self.kls(node_type='foo')
        self.assertRaises(TypeError, base.add_restriction, 42)
        self.assertRaises(TypeError, base.add_restriction)

    def test_init_finalize(self):
        final = self.kls(true, node_type='foo', finalize=True)
        # since it becomes a tuple, throws a AttributeError
        self.assertRaises(TypeError, final.add_restriction, false)

        final = self.kls(true, node_type='foo')
        # since it becomes a tuple, throws a AttributeError
        self.assertRaises(TypeError, final.add_restriction, false)

    def test_finalize(self):
        base = self.kls(true, node_type='foo', finalize=False)
        base.add_restriction(false)
        base.finalize()
        self.assertRaises(TypeError, base.add_restriction, true)

    def test_change_restrictions(self):
        base = self.kls(true, false)
        assert self.kls(false, true) == base.change_restrictions(false, true)
        assert self.kls(false, true) != base.change_restrictions(false, true, negate=True)
        assert self.kls(false, true, negate=True) == base.change_restrictions(false, true, negate=True)

    def test_add_restriction(self):
        self.assertRaises(TypeError,
            self.kls(true, finalize=True).add_restriction, false)
        self.assertRaises(TypeError,
            self.kls(node_type='foon').add_restriction, false)
        k = self.kls(finalize=False)
        k.add_restriction(false)
        assert k.restrictions == [false]

    # TODO total_len? what does it do?

class BaseTest(base, TestCase):

    kls = boolean.base

    def test_base(self):
        base = self.kls(true, false, node_type='foo')
        assert len(base) == 2
        assert list(base) == [true, false]
        self.assertRaises(NotImplementedError, base.match, false)
        # TODO is the signature for these correct?
        self.assertRaises(NotImplementedError, base.force_False, false)
        self.assertRaises(NotImplementedError, base.force_True, false)
        self.assertIdentical(base[1], false)


# TODO these tests are way too limited
class AndRestrictionTest(base, TestCase):

    kls = boolean.AndRestriction

    def test_match(self):
        assert self.kls(true, true, node_type='foo').match(None)
        assert not self.kls(false, true, true, node_type='foo').match(None)
        assert not self.kls(true, false, true, node_type='foo').match(None)

    def test_negate_match(self):
        assert self.kls(false, true, node_type='foo', negate=True).match(None)
        assert self.kls(true, false, node_type='foo', negate=True).match(None)
        assert self.kls(false, false, node_type='foo', negate=True).match(None)
        assert not self.kls(true, true, node_type='foo', negate=True).match(None)

    def test_dnf_solutions(self):
        assert self.kls(true, true).dnf_solutions() == [[true, true]]
        assert self.kls(self.kls(true, true), true).dnf_solutions() == [[true, true, true]]
        assert (list(map(set, self.kls(
                    true, true,
                    boolean.OrRestriction(false, true)).dnf_solutions())) ==
            [set([true, true, false]), set([true, true, true])])
        assert self.kls().dnf_solutions() == [[]]

    def test_cnf_solutions(self):
        assert self.kls(true, true).cnf_solutions() == [[true], [true]]
        assert self.kls(self.kls(true, true), true).cnf_solutions() == [[true], [true], [true]]
        assert (list(self.kls(
                    true, true,
                    boolean.OrRestriction(false, true)).cnf_solutions()) ==
            list([[true], [true], [false, true]]))
        assert self.kls().cnf_solutions() == []


class OrRestrictionTest(base, TestCase):

    kls = boolean.OrRestriction

    def test_match(self):
        assert self.kls(true, true, node_type='foo').match(None)
        assert self.kls(false, true, false, node_type='foo').match(None)
        assert self.kls(true, false, false, node_type='foo').match(None)
        assert self.kls(false, false, true, node_type='foo').match(None)
        assert not self.kls(false, false, node_type='foo').match(None)

    def test_negate_match(self):
        for x in ((true, false), (false, true), (true, true)):
            assert not self.kls(node_type='foo', negate=True, *x).match(None)
        assert self.kls(false, false, node_type='foo', negate=True).match(None)

    def test_dnf_solutions(self):
        assert self.kls(true, true).dnf_solutions() == [[true], [true]]
        assert (list(map(set, self.kls(
                    true, true,
                    boolean.AndRestriction(false, true)).dnf_solutions())) ==
            list(map(set, [[true], [true], [false, true]])))
        assert self.kls(self.kls(true, false), true).dnf_solutions() == [[true], [false], [true]]
        assert self.kls().dnf_solutions() == [[]]

    def test_cnf_solutions(self):
        assert self.kls(true, true).cnf_solutions() == [[true, true]]
        assert ([set(x) for x in self.kls(
                    true, true,
                    boolean.AndRestriction(false, true)).cnf_solutions()] ==
            [set(x) for x in [[true, false], [true, true]]])

        assert ([set(x) for x in self.kls(self.kls(
                        true, true,
                        boolean.AndRestriction(false, true))).cnf_solutions()] ==
            [set(x) for x in [[true, false], [true, true]]])

        assert (set(self.kls(
                    self.kls(true, false),
                    true).cnf_solutions()[0]) ==
            set([true, false, true]))

        assert self.kls().cnf_solutions() == []


class JustOneRestrictionTest(base, TestCase):

    kls = boolean.JustOneRestriction

    def test_match(self):
        assert self.kls(true, false, node_type='foo').match(None)
        assert self.kls(false, true, false, node_type='foo').match(None)
        assert not self.kls(false, false,  node_type='foo').match(None)
        assert not self.kls(true, false, true, node_type='foo').match(None)
        assert not self.kls(true, true, true, node_type='foo').match(None)
