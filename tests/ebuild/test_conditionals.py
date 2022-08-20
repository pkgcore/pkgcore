import pytest

from pkgcore.ebuild import conditionals
from pkgcore.ebuild.atom import atom
from pkgcore.ebuild.errors import DepsetParseError
from pkgcore.restrictions import boolean, packages
from snakeoil.iterables import expandable_chain
from snakeoil.sequences import iflatten_instance


class base:

    class kls(conditionals.DepSet):
        __slots__ = ()
        parse_depset = None

    def gen_depset(self, string, operators=None, element_kls=str,
                   element_func=None, **kwds):
        if element_func is not None:
            kwds["element_func"] = element_func
        if operators is None:
            operators = {"": boolean.AndRestriction, "||": boolean.OrRestriction}
        return self.kls.parse(string, element_kls, operators=operators, **kwds)


class TestDepSetParsing(base):

    @pytest.mark.parametrize("depset", (
        "( )", "( a b c", "(a b c )",
        "( a b c)", "x?( a )",
        "x? (a )", "x? (a)", "x? ( a b)",
        "x? ( x? () )", "x? ( x? (a)", "(", ")", "x?",
        "||(", "||()", "||( )", "|| ()",
        "|| (", "|| )", "||)",  "|| ( x? ( )",
        "|| (x )", "|| ( x)",
        "a|", "a?", "a||b",
        "x? y", "( x )?", "||?"
    ))
    def test_DepsetParseError(self, depset):
        with pytest.raises(DepsetParseError):
            self.gen_depset(depset)

    @staticmethod
    def mangle_cond_payload(p):
        l = [p]
        if isinstance(p, boolean.AndRestriction):
            l = iter(p)
        for x in l:
            s = ""
            if x.negate:
                s = "!"
            for y in x.vals:
                yield s + y

    def flatten_restricts(self, v):
        i = expandable_chain(v)
        depth = 0
        conditionals = []
        for x in i:
            for t, s in ((boolean.OrRestriction, "||"),
                         (boolean.AndRestriction, "&&")):
                if isinstance(x, t):
                    yield s
                    yield "("
                    i.appendleft(")")
                    i.appendleft(x.restrictions)
                    depth += 1
                    break
            else:
                if isinstance(x, packages.Conditional):
                    assert x.attr == "use"
                    conditionals.insert(
                        depth, list(self.mangle_cond_payload(x.restriction)))
                    yield set(iflatten_instance(conditionals[:depth + 1]))
                    yield "("
                    i.appendleft(")")
                    i.appendleft(x.payload)
                    depth += 1
                else:
                    if x == ")":
                        assert depth
                        depth -= 1
                    yield x
        assert not depth

    depsets = (
        "a b",
        ("", []),
        ("( a b )", ("&&", "(", "a", "b", ")")),
        "|| ( a b )",
        ("a || ( a ( b  ) c || ( d )  )",
            ["a", "||", "(", "a", "b", "c", "d", ")"]),
        (" x? ( a  b )", (["x"], "(", "a", "b", ")")),
        ("x? ( y? ( a ) )", (["x"], "(", ["x", "y"], "(", "a", ")", ")")),
        ("|| ( || ( a b ) )", ["||", "(", "a", "b", ")"]),
        "|| ( || ( a b ) c )",
        ("x? ( a !y? ( || ( b c ) d ) e ) f1 f? ( g h ) i", (
            ["x"], "(", "a", ["x", "!y"], "(", "||", "(", "b",
            "c", ")", "d", ")", "e", ")", "f1",
            ["f"], "(", "g", "h", ")", "i"))
    )

    @pytest.mark.parametrize("depset", depsets)
    def test_parse_depset(self, depset):
        if isinstance(depset, (list, tuple)):
            depset, v = depset
            v2 = []
            for idx, x in enumerate(v):
                if isinstance(x, (list, tuple)):
                    v2.append(set(x))
                else:
                    v2.append(x)
            v = v2
        else:
            v = depset.split()
        got = list(self.flatten_restricts(base.gen_depset(self, depset)))
        wanted = list(v)
        assert got == v, "given {s!r}\nexpected {wanted!r} but got {got!r}"

    @pytest.mark.parametrize("depset", depsets)
    def test_depset_str(self, depset):
        if isinstance(depset, (list, tuple)):
            depset, v = depset
            v2 = []
            for x in v:
                if isinstance(x, str):
                    v2.append(x)
                else:
                    v2.append(x[-1] + '?')
            v = ' '.join(v2)
        else:
            v = ' '.join(depset.split())
        v = ' '.join(v.replace("&&", "").split())
        assert str(base.gen_depset(self, depset)) == v

    def check_known_conditionals(self, text, conditionals, **kwds):
        d = self.gen_depset(text, **kwds)
        assert sorted(d.known_conditionals) == sorted(conditionals.split())
        # ensure it does the lookup *once*
        object.__setattr__(d, 'restrictions', ())
        assert not d.restrictions
        assert sorted(d.known_conditionals) == sorted(conditionals.split())

    @pytest.mark.parametrize(("text", "conditionals"), (
        ("a? ( b )", "a"),
        ("a? ( b a? ( c ) )", "a"),
        ("a b c d e ( f )", ""),
        ("!a? ( b? ( c ) )", "a b"),
    ))
    def test_known_conditionals(self, text, conditionals):
        self.check_known_conditionals(text, conditionals)

    def test_known_conditionals_transitive_use(self):
        self.check_known_conditionals(
            "a/b[c=] a/b[!d=] b/a[e?] b/a[!f?]", "c d e f", element_func=atom,
                transitive_use_atoms=True)

        self.check_known_conditionals(
            "|| ( b/a[e?] a/c )", "e", element_func=atom,
                transitive_use_atoms=True)

    def test_element_func(self):
        assert self.gen_depset("asdf fdas", element_func=str).element_class == "".__class__

    def test_disabling_or(self):
        with pytest.raises(DepsetParseError):
            self.gen_depset("|| ( a b )", {"operators": {"": boolean.AndRestriction}})

    def test_atom_interaction(self):
        self.gen_depset("a/b[x(+)]", element_func=atom)


class TestDepSetConditionalsInspection(base):

    def test_sanity_has_conditionals(self):
        assert not bool(self.gen_depset("a b").has_conditionals)
        assert not bool(self.gen_depset("( a b ) || ( c d )").has_conditionals)
        assert bool(self.gen_depset("x? ( a )").has_conditionals)
        assert bool(self.gen_depset("( x? ( a ) )").has_conditionals)
        assert bool(self.gen_depset("|| ( a/b[c=] b/d )", element_kls=atom,
            transitive_use_atoms=True).has_conditionals)

    def flatten_cond(self, c):
        l = set()
        for x in c:
            if isinstance(x, boolean.base):
                assert len(x.dnf_solutions()) == 1
                f = x.dnf_solutions()[0]
            else:
                f = [x]
            t = set()
            for a in f:
                s = ""
                if a.negate:
                    s = "!"
                t.update([f"{s}{y}" for y in a.vals])
            l.add(frozenset(t))
        return l

    def check_conds(self, s, r, element_kls=str, **kwds):
        nc = {k: self.flatten_cond(v) for k, v in
              self.gen_depset(s, element_kls=element_kls, **kwds).node_conds.items()}
        d = {element_kls(k): v for k, v in r.items()}
        for k, v in d.items():
            if isinstance(v, str):
                d[k] = set([frozenset(v.split())])
            elif isinstance(v, (tuple, list)):
                d[k] = set(map(frozenset, v))

        assert nc == d

    @pytest.mark.parametrize(("text", "result"), (
        ("x? ( y )", {"y":"x"}),
        ("x? ( y ) z? ( y )", {"y":["z", "x"]}),
        ("x? ( z? ( w? ( y ) ) )", {"y":"w z x"}),
        ("!x? ( y )", {"y":"!x"}),
        ("!x? ( z? ( y a ) )", {"y":"!x z", "a":"!x z"}),
        ("x ( y )", {}),
        ("x ( y? ( z ) )", {"z":"y"}), # needs to dig down as deep as required
        ("x y? ( x )", {}), # x isn't controlled by a conditional, shouldn't be in the list
        ("|| ( y? ( x ) x )", {}), # x cannot be filtered down since x is accessible via non conditional path
        ("|| ( y? ( x ) z )", {"x":"y"}),
    ))
    def test_node_conds(self, text, result):
        self.check_conds(text, result)

    @pytest.mark.parametrize(("text", "result"), (
        ("a/b[c=]", {"a/b[c]":"c", "a/b[-c]":"!c"}),
    ))
    def test_node_conds_atom(self, text, result):
        self.check_conds(text, result, element_kls=atom, transitive_use_atoms=True)


class TestDepSetEvaluate(base):

    def test_evaluation(self):
        flag_set = list(sorted(f"x{x}" for x in range(2000)))
        for vals in (
            ("y", "x? ( y ) !x? ( z )", "x"),
            ("z", "x? ( y ) !x? ( z )"),
            ("", "x? ( y ) y? ( z )"),
            ("a b", "a !x? ( b )"),
            ("a b", "a !x? ( b )", "", ""),
            ("a b", "a !x? ( b ) y? ( c )", "", "y"),
            ("a || ( b c )", "a || ( x? ( b ) c )", "x"),
            ("a c", "a || ( x? ( b ) c )"),
            ("a", "a x? ( y? ( b ) )"),
            ("a b", "a b"),
            ("a/b[-c]", "a/b[c=]"),
            ("a/b[c]", "a/b[c=]", "c"),
            ("a/b", "a/b[c?]"),
            ("a/b[-c]", "a/b[!c?]"),
            ("a/b", "a/b[!c?]", "c"),
            ("a/b[c]", "a/b[c?]", "c"),
            # this needs to a *very* large number of attributes; what we're asserting here
            # is that the backend doesn't use a quadratic implementation- if it does,
            # we want to preferably blow the allowed stack depth (runtime exception, but that's fine),
            # worst case (jython), we want to force a memory exhaustion.
            # we assert it in the tests to make sure some 'special' ebuild dev doesn't trigger
            # it on a user's machine, thus the abuse leveled here.
            ("a/b", "a/b[!c?,%s]" % (",".join(x + "?" for x in flag_set)), "c"),
            ("a/b", "a/b[%s]" % (",".join("%s?" % (x,) for x in flag_set)), "",
                " ".join(flag_set)),
            ("a/b[c,x0]", "a/b[c?,%s]" % (",".join(x + "?" for x in flag_set)), "c",
                " ".join(flag_set[1:])),
            ("a/b[c,%s]" % (','.join(flag_set),),
                "a/b[c?,%s]" % (",".join(x + "?" for x in flag_set)), "c",
                ""),
            ):

            result = vals[0]
            src = vals[1]
            use, tristate, kls = [], None, str
            if len(vals) > 2:
                use = vals[2].split()
            if len(vals) > 3:
                tristate = vals[3].split()
            kwds = {}
            if '/' in src:
                kls = atom
                flags = src.split("[", 1)[-1]
                if "?" in flags or "=" in flags:
                    kwds['transitive_use_atoms'] = True
            else:
                kls = str
            orig = self.gen_depset(src, element_kls=kls, **kwds)
            collapsed = orig.evaluate_depset(use,
                tristate_filter=tristate)
            assert str(collapsed) == result, \
                f"expected {result!r} got {collapsed!r}\nraw depset: {src!r}\nuse: {use!r}, tristate: {tristate!r}"
            if not ('?' in src or kwds.get("transitive_use_atoms")):
                assert orig is collapsed
