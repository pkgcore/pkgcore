import pytest

from pkgcore.ebuild import atom, misc
from pkgcore.restrictions import packages

AlwaysTrue = packages.AlwaysTrue
AlwaysFalse = packages.AlwaysFalse


class Test_collapsed_restrict_to_data:
    kls = misc.collapsed_restrict_to_data

    def assert_state(self, obj, defaults=(), freeform=(), atoms=()):
        assert set(obj.defaults) == set(defaults)
        assert set(obj.freeform) == set(freeform)
        atoms_dict = {a[0].key: (a, a[1]) for a in atoms}
        assert set(obj.atoms) == set(atoms_dict)
        for k, v in obj.atoms.items():
            l1 = {(x[0], list(x[1])) for x in v}
            l2 = {(x[0], list(x[1])) for x, y in atoms_dict[k]}
            assert l1 == l2, f"for {k!r} atom, got {l1!r}, expected {l2!r}"

    def test_defaults(self):
        srange = list(map(str, range(100)))
        self.assert_state(self.kls([(AlwaysTrue, srange)]), defaults=srange)
        # ensure AlwaysFalse is ignored.
        self.assert_state(self.kls([(AlwaysFalse, srange)]))
        # check always ordering.
        self.assert_state(
            self.kls(
                [(AlwaysTrue, ["x"])], [(AlwaysTrue, ["x", "y"]), (AlwaysTrue, ["-x"])]
            ),
            defaults=["y"],
        )


class TestIncrementalExpansion:
    f = staticmethod(misc.incremental_expansion)

    def test_it(self):
        s = set("ab")
        self.f(("-a", "b", "-b", "-b", "c"), orig=s)
        assert set(s) == {"c"}
        with pytest.raises(ValueError):
            self.f({"-"})

    def test_non_finalized(self):
        s = set("ab")
        self.f(("-a", "b", "-b", "c", "c"), orig=s, finalize=False)
        assert set(s) == {"-a", "-b", "c"}

    def test_starred(self):
        s = set("ab")
        self.f(("c", "-*", "d"), orig=s)
        assert set(s) == {"d"}


def test_IncrementalsDict():
    d = misc.IncrementalsDict(frozenset({"i1", "i2"}), a1="1", i1="1")
    expected = {"a1": "1", "i1": "1"}
    assert d == expected
    d["a1"] = "2"
    expected["a1"] = "2"
    assert d == expected
    assert d
    assert set(d) == {"a1", "i1"}
    assert len(d) == 2
    d["i1"] = "2"
    expected["i1"] = "1 2"
    assert d == expected
    del d["a1"]
    del expected["a1"]
    assert d == expected
    assert d["i1"] == "1 2"
    assert d
    assert set(d) == {"i1"}
    d.clear()
    assert not d
    assert len(d) == 0


class TestChunkedDataInterning:
    def mk_dict(self, *keys):
        # via variables; a tuple literal is folded into a shared constant, which
        # would hide whether interning did anything.
        neg, pos = ["-x"], ["y", "z"]
        d = misc.ChunkedDataDict()
        for key in keys:
            d.update_from_stream(
                [misc.chunked_data(atom.atom(key), tuple(neg), tuple(pos))]
            )
        return d

    @staticmethod
    def chunks(d):
        return [c for v in d.render_to_dict().values() for c in v]

    def test_interner(self):
        interner = misc._interner()
        # via a variable; a tuple literal is folded into a shared constant.
        values = ["y", "z"]
        pos, same_pos = tuple(values), tuple(values)
        assert pos is not same_pos
        a = interner(atom.atom("dev-util/diffball"), (), pos)
        b = interner(atom.atom("dev-util/diffball"), (), same_pos)
        assert a is b
        assert a.pos is pos

    def test_shared_within_a_dict(self):
        d = self.mk_dict("dev-util/diffball", "dev-util/foo")
        assert len({id(c.pos) for c in self.chunks(d)}) == 2
        d.optimize()
        assert len({id(c.pos) for c in self.chunks(d)}) == 1

    def test_shared_across_dicts_via_cache(self):
        # distinct keys, so the existing whole sequence cache can't be what shares them
        cache = {}
        first, second = self.mk_dict("dev-util/diffball"), self.mk_dict("dev-util/foo")
        first.optimize(cache=cache)
        second.optimize(cache=cache)
        assert len({id(c.pos) for c in self.chunks(first) + self.chunks(second)}) == 1

    def test_interning_does_not_alter_values(self):
        plain, interned = (
            self.mk_dict("dev-util/diffball"),
            self.mk_dict("dev-util/diffball"),
        )
        plain.optimize()
        interned.optimize(cache={})
        assert plain.render_to_dict() == interned.render_to_dict()


@pytest.mark.parametrize(
    "expected,source,target",
    [
        ("../../bin/foo", "/bin/foo", "/usr/bin/foo"),
        (
            "../../../doc/foo-1",
            "/usr/share/doc/foo-1",
            "/usr/share/texmf-site/doc/fonts/foo",
        ),
        ("../../opt/bar/foo", "/opt/bar/foo", "/usr/bin/foo"),
        ("../c/d/e", "/a/b/c/d/e", "a/b/f/g"),
        ("b/f", "/a/b///./c/d/../e/..//../f", "/a/././///g/../h"),
        ("../h", "/a/././///g/../h", "/a/b///./c/d/../e/..//../f"),
        (".", "/foo", "/foo/bar"),
        ("..", "/foo", "/foo/bar/baz"),
        ("../../fo . o/b ar", "/fo . o/b ar", "/baz / qu .. ux/qu x"),
        (r'../../f"o\o/b$a[]r', r'/f"o\o/b$a[]r', r'/ba\z/qu$u"x/qux'),
    ],
)
def test_get_relative_dosym_target(expected, source, target):
    assert expected == misc.get_relative_dosym_target(source, target)
