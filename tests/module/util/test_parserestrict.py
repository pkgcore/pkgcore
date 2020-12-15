import pytest
from snakeoil.currying import post_curry

from pkgcore.ebuild import restricts
from pkgcore.ebuild.atom import atom
from pkgcore.repository import util
from pkgcore.restrictions import boolean, packages, restriction, values
from pkgcore.util import parserestrict


class TestMatch:

    def test_comma_separated_containment(self):
        parser = parserestrict.comma_separated_containment('utensil')
        restrict = parser('spork,foon')
        # Icky, should really try to match a fake package.
        assert isinstance(restrict, packages.PackageRestriction)
        assert 'utensil' == restrict.attr
        valrestrict = restrict.restriction
        assert valrestrict.match(('foon',))
        assert not valrestrict.match(('spork,foon',))
        assert not valrestrict.match(('foo',))


class TestExtendedRestrictionGeneration:

    def verify_text_glob(self, restrict, token):
        assert isinstance(restrict, values.StrRegex), token

    def verify_text(self, restrict, token):
        assert isinstance(restrict, values.StrExactMatch), token
        assert restrict.exact == token

    def test_convert_glob(self):
        self.verify_text(parserestrict.convert_glob("diffball"), "diffball")
        for token in ("diff*", "*diff"):
            self.verify_text_glob(parserestrict.convert_glob(token), token)

        for token in ("*", ""):
            i = parserestrict.convert_glob(token)
            assert i == None, (
                f"verifying None is returned on pointless restrictions, failed token: {token}")

        with pytest.raises(parserestrict.ParseError):
            parserestrict.convert_glob('**')

    def verify_restrict(self, restrict, attr, token):
        assert isinstance(restrict, packages.PackageRestriction), token
        assert restrict.attr == attr, (
            f"verifying package attr {restrict.attr}; required({attr}), token {token}")

        if "*" in token:
            self.verify_text_glob(restrict.restriction, token)
        else:
            self.verify_text(restrict.restriction, token)

    def generic_single_restrict_check(self, iscat):
        if iscat:
            sfmts = ["%s/*"]
            attr = "category"
        else:
            sfmts = ["*/%s", "%s"]
            attr = "package"

        for sfmt in sfmts:
            for raw_token in ("package", "*bsdiff", "bsdiff*"):
                token = sfmt % raw_token
                i = parserestrict.parse_match(token)
                self.verify_restrict(i, attr, raw_token)

    test_category = post_curry(generic_single_restrict_check, True)
    test_package = post_curry(generic_single_restrict_check, False)

    def test_combined(self):
        assert isinstance(parserestrict.parse_match("dev-util/diffball"), atom), "dev-util/diffball"
        for token in ("dev-*/util", "dev-*/util*", "dev-a/util*"):
            i = parserestrict.parse_match(token)
            assert isinstance(i, boolean.AndRestriction), token
            assert len(i) == 2
            self.verify_restrict(i[0], "category", token.split("/")[0])
            self.verify_restrict(i[1], "package", token.split("/")[1])

    def test_globs(self):
        for token in ("*", "*/*"):
            i = parserestrict.parse_match(token)
            assert isinstance(i, restriction.AlwaysBool), token
            assert len(i) == 1

        for token in ("*::gentoo", "*/*::gentoo"):
            i = parserestrict.parse_match(token)
            assert isinstance(i, boolean.AndRestriction), token
            assert len(i) == 2
            assert isinstance(i[0], restricts.RepositoryDep), token.split("::")[1]
            assert isinstance(i[1], restriction.AlwaysBool), token.split("::")[0]

        for token in ("foo*::gentoo", "*foo::gentoo"):
            i = parserestrict.parse_match(token)
            assert isinstance(i, boolean.AndRestriction), token
            assert len(i) == 2
            assert isinstance(i[0], restricts.RepositoryDep), token.split("::")[1]
            self.verify_restrict(i[1], "package", token.split("::")[0])

        for token, attr, n in (
                ('foo/*:5', 'category', 0),
                ('*/foo:5', 'package', 1),
                ):
            i = parserestrict.parse_match(token)
            assert isinstance(i, boolean.AndRestriction), token
            assert len(i) == 2
            assert isinstance(i[0], restricts.SlotDep), token.split(":")[1]
            self.verify_restrict(i[1], attr, token.split(":")[0].split("/")[n])

        for token, attr, n in (
                ('foo/*:5/5', 'category', 0),
                ('*/foo:5/5', 'package', 1),
                ):
            i = parserestrict.parse_match(token)
            assert isinstance(i, boolean.AndRestriction), token
            assert len(i) == 3
            slot, _sep, subslot = token.split(":")[1].partition('/')
            assert isinstance(i[0], restricts.SlotDep), slot
            assert isinstance(i[1], restricts.SubSlotDep), subslot
            self.verify_restrict(i[2], attr, token.split(":")[0].split("/")[n])

        for token, attr, n in (
                ("foo/*::gentoo", "category", 0),
                ("*/foo::gentoo", "package", 1),
                ):
            i = parserestrict.parse_match(token)
            assert isinstance(i, boolean.AndRestriction), token
            assert len(i) == 2
            assert isinstance(i[0], restricts.RepositoryDep), token.split("::")[1]
            self.verify_restrict(i[1], attr, token.split("::")[0].split("/")[n])

        for token, attr, n in (
                ('foo/*:5/5::gentoo', 'category', 0),
                ('*/foo:5/5::gentoo', 'package', 1),
                ):
            i = parserestrict.parse_match(token)
            assert isinstance(i, boolean.AndRestriction), token
            assert len(i) == 4
            token, repo_id = token.rsplit('::', 1)
            assert isinstance(i[0], restricts.RepositoryDep), repo_id
            slot, _sep, subslot = token.split(":")[1].partition('/')
            assert isinstance(i[1], restricts.SlotDep), slot
            assert isinstance(i[2], restricts.SubSlotDep), subslot
            self.verify_restrict(i[3], attr, token.split(":")[0].split("/")[n])

    def test_atom_globbed(self):
        assert isinstance(
            parserestrict.parse_match("=sys-devel/gcc-4*"), atom), "=sys-devel/gcc-4*"

    def test_use_atom(self):
        o = parserestrict.parse_match("net-misc/openssh[-X]")
        assert isinstance(o, atom), "net-misc/openssh[-X]"
        assert o.use

    def test_slot_atom(self):
        o = parserestrict.parse_match("sys-devel/automake:1.6")
        assert isinstance(o, atom), "sys-devel/automake:1.6"
        assert o.slot

    def test_subslot_atom(self):
        o = parserestrict.parse_match("dev-libs/boost:0/1.54")
        assert isinstance(o, atom), "dev-libs/boost:0/1.54"
        assert o.slot
        assert o.subslot

    def test_subslot_package(self):
        token = 'boost:0/1.54'
        o = parserestrict.parse_match(token)
        assert isinstance(o, boolean.AndRestriction), token
        assert len(o) == 3
        slot, _sep, subslot = token.split(":")[1].partition('/')
        assert isinstance(o[0], restricts.SlotDep), slot
        assert isinstance(o[1], restricts.SubSlotDep), subslot
        self.verify_restrict(o[2], "package", token.split(":")[0])

    def test_exceptions(self):
        for token in (
                "!dev-util/diffball",
                "dev-util/diffball-0.4",
                "=dev-util/*diffball-0.4*",
                "::gentoo",
                ):
            with pytest.raises(parserestrict.ParseError):
                parserestrict.parse_match(token)


class TestParsePV:

    def setup_method(self, method):
        self.repo = util.SimpleTree({
            'spork': {
                'foon': ('1', '2'),
                'spork': ('1', '2'),
                },
            'foon': {
                'foon': ('2', '3'),
                }})

    def test_parse_pv(self):
        for input, output in (
                ('spork/foon-3', 'spork/foon-3'),
                ('spork-1', 'spork/spork-1'),
                ('foon-3', 'foon/foon-3'),
                ):
            assert output == parserestrict.parse_pv(self.repo, input).cpvstr
        for bogus in (
                'spork',
                'foon-2',
                ):
            with pytest.raises(parserestrict.ParseError):
                parserestrict.parse_pv(self.repo, bogus)
