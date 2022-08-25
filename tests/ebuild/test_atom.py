from functools import partial
from pickle import dumps, loads

import pytest

from pkgcore.ebuild import atom, errors, restricts
from pkgcore.ebuild.cpv import CPV
from pkgcore.restrictions.boolean import AndRestriction
from pkgcore.test.misc import FakePkg, FakeRepo
from snakeoil.compatibility import cmp

from ..restrictions.utils import TestRestriction

def assert_equal_bidirectional(o1, o2):
    # logic bugs hidden behind short circuiting comparisons for metadata
    # is why we test the comparison *both* ways.
    assert o1 == o2
    assert cmp(o1, o2) == 0
    assert o2 == o1
    assert cmp(o2, o1) == 0

def assert_not_equal_bidirectional(o1, o2):
    # is why we test the comparison *both* ways.
    assert o1 != o2
    assert cmp(o1, o2) != 0
    assert o2 != o1
    assert cmp(o2, o1) != 0

class TestAtom(TestRestriction):

    class kls(atom.atom):
        __inst_caching__ = True
        __slots__ = ()

    kls = staticmethod(kls)

    def test_removed_features(self):
        # Ensure multi-slots no longer are allowed.
        pytest.raises(errors.MalformedAtom, self.kls, "dev-util/diffball:1,2")
        assert self.kls("dev-util/diffball:1").slot == "1"

    def test_solutions(self):
        d = self.kls("=dev-util/diffball-0.7.1:2")
        assert list(d.iter_dnf_solutions()) == [[d]]
        assert d.dnf_solutions() == [[d]]
        assert list(d.iter_cnf_solutions()) == [[d]]
        assert d.cnf_solutions() == [[d]]
        bd = AndRestriction(*d.restrictions)
        assert list(d.iter_dnf_solutions(True)) == bd.dnf_solutions()
        assert list(d.iter_cnf_solutions(True)) == bd.cnf_solutions()
        assert d.dnf_solutions(True) == bd.dnf_solutions()
        assert d.cnf_solutions(True) == bd.cnf_solutions()

    @pytest.mark.parametrize("atom", (
        "dev-util/diffball", "=dev-util/diffball-0.7.1",
        ">foon/bar-1:2[-4,3]", "=foon/bar-2*", "~foon/bar-2.3",
        "cat/pkg:0", "cat/pkg:5", "cat/pkg:0/5", "cat/pkg:5/5",
        "cat/pkg:=", "cat/pkg:0=", "cat/pkg:*",
        "!dev-util/diffball", "!=dev-util/diffball-0.7*",
        "foon/bar::gentoo", ">=foon/bar-10_alpha1:1::gentoo[-not,use]",
        "!!dev-util/diffball[use]",
    ))
    def test_str_hash(self, atom):
        assert str(self.kls(atom)) == atom
        assert hash(self.kls(atom, disable_inst_caching=True)) == hash(self.kls(atom, disable_inst_caching=True))

    def test_blockers(self):
        pytest.raises(errors.MalformedAtom, self.kls,
            "!!dev-util/diffball", eapi='0')
        pytest.raises(errors.MalformedAtom, self.kls,
            "!!dev-util/diffball", eapi='1')
        pytest.raises(errors.MalformedAtom, self.kls,
            "!!!dev-util/diffball", eapi='2')
        for x in range(0, 2):
            obj = self.kls("!dev-util/diffball", eapi=str(x))
            assert obj.blocks
            assert obj.blocks_temp_ignorable
            assert not obj.blocks_strongly
        obj = self.kls("!!dev-util/diffball", eapi='2')
        assert obj.blocks
        assert not obj.blocks_temp_ignorable
        assert obj.blocks_strongly


    def test_iter(self):
        d = self.kls("!>=dev-util/diffball-0.7:1::gentoo[use,x]")
        assert list(d) == list(d.restrictions)

    def test_pickling(self):
        a = self.kls("dev-util/diffball")
        assert a == loads(dumps(a))
        a = self.kls("dev-util/diffball", negate_vers=True)
        assert a == loads(dumps(a))

    def test_glob(self):
        pytest.raises(errors.MalformedAtom, self.kls,
            "dev-util/diffball-1*")
        pytest.raises(errors.MalformedAtom, self.kls,
            "dev-util/diffball-1.*")
        pytest.raises(errors.MalformedAtom, self.kls,
            "~dev-util/diffball-1*")
        pytest.raises(errors.MalformedAtom, self.kls,
            "~dev-util/diffball-1.*")

        a = self.kls("=dev-util/diffball-1.2*")
        self.assertMatch(a, FakePkg("dev-util/diffball-1.2"))
        self.assertMatch(a, FakePkg("dev-util/diffball-1.2.0"))
        self.assertMatch(a, FakePkg("dev-util/diffball-1.2-r1"))
        self.assertMatch(a, FakePkg("dev-util/diffball-1.2_alpha"))
        self.assertNotMatch(a, FakePkg("dev-util/diffball-1"))

    def test_nonversioned(self):
        a = self.kls("kde-base/kde")
        self.assertMatch(a, CPV.unversioned("kde-base/kde"))
        self.assertNotMatch(a, CPV.unversioned("kde-base/kde2"))
        self.assertMatch(a, CPV.versioned("kde-base/kde-3"))

    def make_atom(self, s, ops, ver):
        l = []
        if -1 in ops:
            l.append(">")
        if 0 in ops:
            l.append("=")
        if 1 in ops:
            l.append("<")
        return self.kls(f"{''.join(l)}{s}-{ver}")

    def test_versioned(self):
        astr = "app-arch/tarsync"
        le_cpv = CPV.versioned(f"{astr}-0")
        eq_cpv = CPV.versioned(f"{astr}-1.1-r2")
        ge_cpv = CPV.versioned(f"{astr}-2")
        # <, =, >
        ops = (-1, 0, 1)

        for ops, ver in ((-1, "1.0"), (-1, "1.1"),
            (0, "1.1-r2"), (1, "1.1-r3"), (1, "1.2")):
            if not isinstance(ops, (list, tuple)):
                ops = (ops,)
            a = self.make_atom(astr, ops, ver)
            if -1 in ops:
                self.assertMatch(a, ge_cpv)
                self.assertMatch(a, eq_cpv)
                self.assertNotMatch(a, le_cpv)
            if 0 in ops:
                assert a.match(eq_cpv)
                if ops == (0,):
                    self.assertNotMatch(a, le_cpv)
                    self.assertNotMatch(a, ge_cpv)
            if 1 in ops:
                self.assertNotMatch(a, ge_cpv)
                self.assertMatch(a, eq_cpv)
                self.assertMatch(a, le_cpv)

    def test_norev(self):
        astr = "app-arch/tarsync"
        a = self.kls(f"~{astr}-1")
        self.assertMatch(a, CPV.versioned(f"{astr}-1"))
        self.assertMatch(a, CPV.versioned(f"{astr}-1-r1"))
        self.assertMatch(a, CPV.versioned(f"{astr}-1-r0"))
        self.assertNotMatch(a, CPV.versioned(f"{astr}-2"))
        pytest.raises(errors.MalformedAtom, self.kls, f"~{astr}-1-r1")
        pytest.raises(errors.MalformedAtom, self.kls, f"~{astr}-1-r2")
        # special case- yes -r0 effectively is None, but -r shouldn't be used
        # with ~
        pytest.raises(errors.MalformedAtom, self.kls, f"~{astr}-1-r0")

    @pytest.mark.parametrize(("eapi", "defaults"), (
        (2, False), (3, False),
        (4, True), (5, True), (6, True), (7, True), (8, True),
    ))
    def test_eapi_use(self, eapi, defaults):
        astr = "dev-util/bsdiff"
        c = FakePkg(f"{astr}-1", use=("debug",), iuse=("debug", "foon"), slot=1)

        kls = partial(self.kls, eapi=str(eapi))

        # Valid chars: [a-zA-Z0-9_@+-]
        for use_text in (
            '[zZaA09]', '[x@y]', '[x+y]', '[x-y]', '[x_y]',
            '[-x_y]', '[x?]', '[!x?]', '[x=]', '[!x=]',
        ):
            kls(f'{astr}{use_text}')

        if defaults:
            kls(f'{astr}[x(+)]')
            kls(f'{astr}[x(-)]')
            with pytest.raises(errors.MalformedAtom):
                kls(f'{astr}[x(+-)]')
            with pytest.raises(errors.MalformedAtom):
                kls(f'{astr}[x(@)]')
            self.assertMatch(kls(f"{astr}[debug(+)]"), c)
            self.assertMatch(kls(f"{astr}[debug(-)]"), c)
            self.assertMatch(kls(f"{astr}[missing(+)]"), c)
            self.assertNotMatch(kls(f"{astr}[missing(-)]"), c)
            self.assertMatch(kls(f"{astr}[missing(+)]"), c)
            self.assertMatch(kls(f"{astr}[-missing(-)]"), c)
            self.assertNotMatch(kls(f"{astr}[-missing(+)]"), c)

            self.assertMatch(kls(f"{astr}[-missing(-),debug]"), c)
            self.assertNotMatch(kls(f"{astr}[-missing(+),debug(+)]"), c)
            self.assertMatch(kls(f"{astr}[missing(+),debug(+)]"), c)
        else:
            with pytest.raises(errors.MalformedAtom):
                kls(f'{astr}[x(+)]')
            with pytest.raises(errors.MalformedAtom):
                kls(f'{astr}[x(-)]')

        for use_text in (
            # '.' not a valid char in use deps
            "[x.y]",
            # Use deps start with an alphanumeric char (non-transitive)
            "[@x]", "[_x]", "[+x]", "[-@x]", "[-_x]", "[-+x]", "[--x]",
        ):
            with pytest.raises(errors.MalformedAtom):
                kls(f"{astr}{use_text}")

        self.assertMatch(kls(f"{astr}[debug]"), c)
        self.assertNotMatch(kls(f"{astr}[-debug]"), c)
        self.assertMatch(kls(f"{astr}[debug,-not]"), c)
        self.assertMatch(kls(f"{astr}:1[debug,-not]"), c)

        for atom in (
            f"{astr}[]",
            f"{astr}[-]",
            "dev-util/diffball[foon",
            "dev-util/diffball[[fo]",
            "dev-util/diffball[x][y]",
            "dev-util/diffball[x]:1",
            "dev-util/diffball[x]a",
            "dev-util/diffball[--]",
            "dev-util/diffball[x??]",
            "dev-util/diffball[x=?]",
            "dev-util/diffball[x?=]",
            "dev-util/diffball[x==]",
            "dev-util/diffball[x??]",
            "dev-util/diffball[!=]",
            "dev-util/diffball[!?]",
            "dev-util/diffball[!!x?]",
            "dev-util/diffball[!-x?]",
        ):
            with pytest.raises(errors.MalformedAtom):
                kls(atom)

    def test_slot(self):
        astr = "dev-util/confcache"
        c = FakePkg(f"{astr}-1", slot=1)
        self.assertNotMatch(self.kls(f"{astr}:0"), c)
        self.assertMatch(self.kls(f"{astr}:1"), c)
        self.assertNotMatch(self.kls(f"{astr}:2"), c)
        # note the above isn't compliant with eapi2/3; thus this test
        with pytest.raises(errors.MalformedAtom):
            self.kls("dev-util/foo:0", eapi='0')

        # shouldn't puke, but has, thus checking"
        self.kls("sys-libs/db:4.4")
        self.kls(f"{astr}:azAZ.-+_09")
        self.kls(f"{astr}:_bar") # According to PMS, underscore and plus-sign are
        self.kls(f"{astr}:+bar") # not invalid first chars in a slot dep

    @pytest.mark.parametrize("atom", (
        "dev-util/foo:",
        "dev-util/foo:1,,0",
        "dev-util/foo:1:",
        "dev-util/foo:-1",
        "dev-util/foo:.1",
        "dev-util/foo:1@2",
        "dev-util/foo[bar]:1",
    ))
    def test_slot_malformed_atom(self, atom):
        with pytest.raises(errors.MalformedAtom):
            self.kls(atom)

    def test_slot_operators_and_subslots(self):
        pytest.raises(errors.MalformedAtom, self.kls, "sys-libs/db:*", eapi='4')
        self.kls("sys-libs/db:*", eapi='5')
        pytest.raises(errors.MalformedAtom, self.kls, "sys-libs/db:=", eapi='4')
        self.kls("sys-libs/db:=", eapi='5')
        pytest.raises(errors.MalformedAtom, self.kls, "sys-libs/db:==", eapi='5')
        pytest.raises(errors.MalformedAtom, self.kls, "sys-libs/db:1=", eapi='4')
        pytest.raises(errors.MalformedAtom, self.kls, "sys-libs/db:2/3.0=", eapi='4')
        pytest.raises(errors.MalformedAtom, self.kls, "sys-libs/db:2/3.0", eapi='1')
        pytest.raises(errors.MalformedAtom, self.kls, "sys-libs/db:/=", eapi='5')
        pytest.raises(errors.MalformedAtom, self.kls, "sys-libs/db:/1=", eapi='5')
        pytest.raises(errors.MalformedAtom, self.kls, "sys-libs/db:1/=", eapi='5')
        pytest.raises(errors.MalformedAtom, self.kls, "sys-libs/db:*1/=", eapi='5')

        for subslot in ("/1.0", ""):
            pytest.raises(errors.MalformedAtom, self.kls, f"sys-libs/db:*4{subslot}", eapi='5')
            pytest.raises(errors.MalformedAtom, self.kls, f"sys-libs/db:4{subslot}*", eapi='5')
            pytest.raises(errors.MalformedAtom, self.kls, f"sys-libs/db:=4{subslot}", eapi='5')
            self.kls(f"sys-libs/db:4{subslot}=", eapi='5')
            self.kls(f"sys-libs/db:3.2{subslot}=", eapi='5')
            pytest.raises(errors.MalformedAtom, self.kls, f"sys-libs/db:4{subslot}==", eapi='5')

        def check_it(text, slot, subslot, operator):
            obj = self.kls(f"sys-libs/db{text}")
            assert obj.slot == slot
            assert obj.subslot == subslot
            assert obj.slot_operator == operator
        check_it(":4", "4", None, None)
        check_it(":=", None, None, "=")
        check_it(":4=", "4", None, "=")
        check_it(":4/0.4=", "4", "0.4", "=")
        check_it(":*", None, None, "*")

        # Verify restrictions.
        self.assertMatch(self.kls("sys-libs/db:1="),
            FakePkg("sys-libs/db-1", slot="1"))
        self.assertMatch(self.kls("sys-libs/db:1/2="),
            FakePkg("sys-libs/db-1", slot="1", subslot="2"))
        self.assertNotMatch(self.kls("sys-libs/db:1/2.3="),
            FakePkg("sys-libs/db-1", slot="1", subslot="2"))
        self.assertNotMatch(self.kls("sys-libs/db:1/2.3="),
            FakePkg("sys-libs/db-1", slot="1"))
        self.assertMatch(self.kls("sys-libs/db:1a.2/2.3"),
            FakePkg("sys-libs/db-1", slot="1a.2", subslot="2.3"))

    def test_getattr(self):
        # assert it explodes for bad attr access.
        obj = self.kls("dev-util/diffball")
        with pytest.raises(AttributeError):
            obj.__foasdfawe

        # assert ordering
        def assertAttr(attr):
            assert restrictions[pos].attr == attr, (
                f"expected attr {attr!r} at {pos} for ver({ver}), repo({repo}) use({use}), "
                f"slot({slot}): got {restrictions[pos].attr!r} from {restrictions!r}")
            return pos + 1

        slot = ''
        def f():
            for pref, ver in (('', ''), ('=', '-0.1')):
                for repo in ('', '::gentoo'):
                    for slot in ('', ':1'):
                        for use in ('', '[x]'):
                            yield pref, ver, repo, slot, use

        for pref, ver, repo, slot, use in f():
            pos = 0
            o = self.kls(f"{pref}dev-util/diffball{ver}{slot}{repo}{use}")
            count = 2
            for x in ("use", "repo", "pref", "slot"):
                if locals()[x]:
                    count += 1

            restrictions = o.restrictions
            assert len(restrictions) == count
            assert [getattr(x, 'type', None) for x in restrictions] == ['package'] * count
            if repo:
                pos = assertAttr('repo.repo_id')
            pos = assertAttr('package')
            pos = assertAttr('category')
            if ver:
                assert isinstance(restrictions[pos], restricts.VersionMatch)
                pos += 1
            if slot:
                pos = assertAttr('slot')
            if use:
                pos = assertAttr('use')

    def test_eapi0(self):
        for postfix in (':1', ':1,2', ':asdf', '::asdf', '::asdf-x86', '[x]',
                        '[x,y]', ':1[x,y]', '[x,y]:1', ':1::repo'):
            with pytest.raises(errors.MalformedAtom):
                # "dev-util/foon{postfix} must be invalid in EAPI 0",
                self.kls(f"dev-util/foon{postfix}", eapi='0')

    def test_eapi1(self):
        for postfix in (':1,2', '::asdf', '::asdf-x86', '[x]',
                        '[x,y]', ':1[x,y]', '[x,y]:1', ':1:repo'):
            with pytest.raises(errors.MalformedAtom):
                # "dev-util/foon{postfix} must be invalid in EAPI 1"
                self.kls(f"dev-util/foon{postfix}", eapi='1')
        self.kls("dev-util/foon:1", eapi='1')
        self.kls("dev-util/foon:12", eapi='1')
        with pytest.raises(errors.MalformedAtom):
            # "dev-util/foon[dar] must be invalid in EAPI 1"
            self.kls("dev-util/foon:1,2", eapi='1')

    def test_eapi3(self):
        self.kls("dev-util/foon:1", eapi='3')
        self.kls("dev-util/foon:2", eapi='3')
        self.kls("!dev-util/foon:1", eapi='3')
        self.kls("dev-util/foon:1[x]", eapi='3')
        self.kls("dev-util/foon:1[x?]", eapi='3')
        with pytest.raises(errors.MalformedAtom):
            self.kls("dev-util/foon:1::dar", eapi='3')

    def test_repo_id(self):
        astr = "dev-util/bsdiff"
        c = FakePkg(f"{astr}-1", repo=FakeRepo(repo_id="gentoo-x86A_"), slot="0")
        self.assertMatch(self.kls(f"{astr}"), c)
        self.assertMatch(self.kls(f"{astr}::gentoo-x86A_"), c)
        self.assertMatch(self.kls(f"{astr}:0::gentoo-x86A_"), c)
        self.assertNotMatch(self.kls(f"{astr}::gentoo2"), c)
        with pytest.raises(errors.MalformedAtom):
            self.kls("dev-util/foon:1:")
        with pytest.raises(errors.MalformedAtom):
            self.kls("dev-util/foon::")
        with pytest.raises(errors.MalformedAtom):
            self.kls("dev-util/foon::-gentoo-x86")
        with pytest.raises(errors.MalformedAtom):
            self.kls("dev-util/foon:::")
        for x in range(0, 3):
            with pytest.raises(errors.MalformedAtom):
                self.kls("dev-util/foon::gentoo-x86", eapi=str(x))

    @pytest.mark.parametrize("atom", (
        '~dev-util/spork', '>dev-util/spork', 'dev-util/spork-3', 'spork'
    ))
    def test_invalid_atom(self, atom):
        with pytest.raises(errors.MalformedAtom):
            self.kls(atom)

    @pytest.mark.parametrize(("this", "that", "result"), (
        ('cat/pkg', 'pkg/cat', False),
        ('cat/pkg', 'cat/pkg', True),
        ('cat/pkg:1', 'cat/pkg:2', False),
        ('cat/pkg:1', 'cat/pkg:1', True),
        ('cat/pkg:1', 'cat/pkg[foo]', True),
        ('cat/pkg:0/0', 'cat/pkg:0/1', False),
        ('cat/pkg:0/0', 'cat/pkg:0/0', True),
        ('cat/pkg:0/0', 'cat/pkg:0', True),
        ('cat/pkg:0/0', 'cat/pkg', True),
        ('cat/pkg[foo]', 'cat/pkg[-bar]', True),
        ('cat/pkg[foo]', 'cat/pkg[-foo]', False),
        ('>cat/pkg-3', '>cat/pkg-1', True),
        ('>cat/pkg-3', '<cat/pkg-3', False),
        ('>=cat/pkg-3', '<cat/pkg-3', False),
        ('>cat/pkg-2', '=cat/pkg-2*', True),
        ('<cat/pkg-2_alpha1', '=cat/pkg-2*', True),
        ('=cat/pkg-2', '=cat/pkg-2', True),
        ('=cat/pkg-3', '=cat/pkg-2', False),
        ('=cat/pkg-2', '>cat/pkg-2', False),
        ('=cat/pkg-2', '>=cat/pkg-2', True),
        ('~cat/pkg-2', '~cat/pkg-2', True),
        ('~cat/pkg-2', '~cat/pkg-2.1', False),
        ('=cat/pkg-2*', '=cat/pkg-2.3*', True),
        ('>cat/pkg-2.4', '=cat/pkg-2*', True),
        ('<cat/pkg-2.4', '=cat/pkg-2*', True),
        ('<cat/pkg-1', '=cat/pkg-2*', False),
        ('~cat/pkg-2', '>cat/pkg-2-r1', True),
        ('~cat/pkg-2', '<=cat/pkg-2', True),
        ('=cat/pkg-2-r2*', '<=cat/pkg-2-r20', True),
        ('=cat/pkg-2-r2*', '<cat/pkg-2-r20', True),
        ('=cat/pkg-2-r2*', '<=cat/pkg-2-r2', True),
        ('~cat/pkg-2', '<cat/pkg-2', False),
        ('=cat/pkg-1-r10*', '~cat/pkg-1', True),
        ('=cat/pkg-1-r1*', '<cat/pkg-1-r1', False),
        ('=cat/pkg-1*', '>cat/pkg-2', False),
        ('>=cat/pkg-8.4', '=cat/pkg-8.3.4*', False),
        ('cat/pkg::gentoo', 'cat/pkg', True),
        ('cat/pkg::gentoo', 'cat/pkg::foo', False),
        # known to cause an assplosion, thus redundant test.
        ('=sys-devel/gcc-4.1.1-r3', '=sys-devel/gcc-3.3*', False),
        ('=sys-libs/db-4*', '~sys-libs/db-4.3.29', True),
    ))
    def test_intersects(self, this, that, result):
        this_atom = self.kls(this)
        that_atom = self.kls(that)
        assert result == this_atom.intersects(that_atom), f'{this} intersecting {that} should be {result}'
        assert result == that_atom.intersects(this_atom), f'{that} intersecting {this} should be {result}'


    def test_comparison(self):
        assert_equal_bidirectional(self.kls('cat/pkg'), self.kls('cat/pkg'))
        assert_not_equal_bidirectional(self.kls('cat/pkg'), self.kls('cat/pkgb'))
        assert_not_equal_bidirectional(self.kls('cata/pkg'), self.kls('cat/pkg'))
        assert_not_equal_bidirectional(self.kls('cat/pkg'), self.kls('!cat/pkg'))
        assert_equal_bidirectional(self.kls('!cat/pkg'), self.kls('!cat/pkg'))
        assert_not_equal_bidirectional(self.kls('=cat/pkg-0.1:0'), self.kls('=cat/pkg-0.1'))
        assert_not_equal_bidirectional(self.kls('=cat/pkg-1[foon]'), self.kls('=cat/pkg-1'))
        assert_equal_bidirectional(self.kls('=cat/pkg-0'), self.kls('=cat/pkg-0'))
        assert_not_equal_bidirectional(self.kls('<cat/pkg-2'), self.kls('>cat/pkg-2'))
        assert_not_equal_bidirectional(self.kls('=cat/pkg-2*'), self.kls('=cat/pkg-2'))
        assert_not_equal_bidirectional(self.kls('=cat/pkg-2', True), self.kls('=cat/pkg-2'))

        # use...
        assert_not_equal_bidirectional(self.kls('cat/pkg[foo]'), self.kls('cat/pkg'))
        assert_not_equal_bidirectional(self.kls('cat/pkg[foo]'), self.kls('cat/pkg[-foo]'))
        assert_equal_bidirectional(self.kls('cat/pkg[foo,-bar]'), self.kls('cat/pkg[-bar,foo]'))
        # repo_id
        assert_equal_bidirectional(self.kls('cat/pkg::a'), self.kls('cat/pkg::a'))
        assert_not_equal_bidirectional(self.kls('cat/pkg::a'), self.kls('cat/pkg::b'))
        assert_not_equal_bidirectional(self.kls('cat/pkg::a'), self.kls('cat/pkg'))

        # slots.
        assert_not_equal_bidirectional(self.kls('cat/pkg:1'), self.kls('cat/pkg'))
        assert_equal_bidirectional(self.kls('cat/pkg:2'), self.kls('cat/pkg:2'))
        for lesser, greater in (('0.1', '1'), ('1', '1-r1'), ('1.1', '1.2')):
            assert self.kls(f'=d/b-{lesser}') < self.kls(f'=d/b-{greater}'), \
                f"d/b-{lesser} < d/b-{greater}"
            assert not (self.kls(f'=d/b-{lesser}') > self.kls(f'=d/b-{greater}')), \
                f"!: d/b-{lesser} < d/b-{greater}"
            assert self.kls(f'=d/b-{greater}') > self.kls(f'=d/b-{lesser}'), \
                f"d/b-{greater} > d/b-{lesser}"
            assert not (self.kls(f'=d/b-{greater}') < self.kls(f'=d/b-{lesser}')), \
                f"!: d/b-{greater} > d/b-{lesser}"

        assert self.kls("!!=d/b-1", eapi='2') > self.kls("!=d/b-1")
        assert self.kls("!=d/b-1") < self.kls("!!=d/b-1")
        assert self.kls("!=d/b-1") == self.kls("!=d/b-1")

    def test_compatibility(self):
        self.assertNotMatch(self.kls('=dev-util/diffball-0.7'),
            FakePkg('dev-util/diffball-0.7.0'))
        # see bug http://bugs.gentoo.org/152127
        self.assertNotMatch(self.kls('>=sys-apps/portage-2.1.0_pre3-r5'),
            FakePkg('sys-apps/portage-2.1_pre3-r5'))

    def test_combined(self):
        p = FakePkg('dev-util/diffball-0.7', repo=FakeRepo(repo_id='gentoo'))
        self.assertMatch(self.kls('=dev-util/diffball-0.7::gentoo'), p)
        self.assertMatch(self.kls('dev-util/diffball::gentoo'), p)
        self.assertNotMatch(self.kls('=dev-util/diffball-0.7:1::gentoo'),
            FakePkg('dev-util/diffball-0.7', slot='2'))

    def test_unversioned(self):
        assert self.kls("dev-util/diffball").is_simple
        assert not self.kls("dev-util/diffball:2").is_simple
        assert not self.kls("dev-util/diffball:2::gentoo").is_simple
        assert not self.kls("dev-util/diffball::gentoo").is_simple
        assert not self.kls("!=dev-util/diffball-1").is_simple
        assert not self.kls(">dev-util/diffball-1.2").is_simple
        assert not self.kls("=dev-util/diffball-1").is_simple
        assert not self.kls("dev-util/diffball[x]").is_simple
        assert not self.kls("dev-util/diffball[x?]").is_simple

    @pytest.mark.parametrize(("original", "wanted"), (
        ("<dev-util/diffball-2", "<dev-util/diffball-2"),
        ("<dev-util/diffball-2[debug=,test=]", "<dev-util/diffball-2"),
        ("=dev-util/diffball-2", "=dev-util/diffball-2"),
        ("=dev-util/diffball-2[debug=,test=]", "=dev-util/diffball-2"),
        ("=dev-util/diffball-2*", "=dev-util/diffball-2*"),
        ("=dev-util/diffball-2*[debug=,test=]", "=dev-util/diffball-2*"),
        ("dev-util/diffball:0", "dev-util/diffball:0"),
        ("dev-util/diffball:0[debug=,test=]", "dev-util/diffball:0"),
        ("dev-util/diffball:0/1.12", "dev-util/diffball:0/1.12"),
        ("dev-util/diffball:0/1.12[debug=,test=]", "dev-util/diffball:0/1.12"),
        ("!dev-util/diffball", "!dev-util/diffball"),
        ("!dev-util/diffball[debug=,test=]", "!dev-util/diffball"),
        ("!!dev-util/diffball", "!!dev-util/diffball"),
        ("!!dev-util/diffball[debug=,test=]", "!!dev-util/diffball"),
    ))
    def test_get_atom_without_use_deps(self, original, wanted):
        orig_atom = self.kls(original)
        assert str(orig_atom.get_atom_without_use_deps) == wanted
