from itertools import islice

import pytest

from pkgcore.ebuild.eapi import get_eapi
from pkgcore.ebuild.ebuild_src import base as ebuild
from pkgcore.restrictions.required_use import find_constraint_satisfaction as solver


def parse(required_use):
    o = ebuild(None, "dev-util/diffball-0.1-r1")
    object.__setattr__(o, "eapi", get_eapi("8", suppress_unsupported=True))
    object.__setattr__(o, "data", {"REQUIRED_USE": required_use})
    return o.required_use


def test_simple():
    required_use = parse(required_use="bar foo")
    assert tuple(solver(required_use, {"bar", "foo"})) == ({"bar": True, "foo": True},)


def test_negative_simple():
    required_use = parse(required_use="!bar foo")
    assert tuple(solver(required_use, {"bar", "foo"})) == ({"bar": False, "foo": True},)


def test_missing_iuse():
    required_use = parse(required_use="!bar foo? ( bar )")
    assert tuple(solver(required_use, {"bar"})) == ({"bar": False, "foo": False},)


@pytest.mark.parametrize(
    ("required_use", "exclude"),
    (
        ("bar? ( foo )", {"bar": True, "foo": False}),
        ("bar? ( !foo )", {"bar": True, "foo": True}),
        ("!bar? ( foo )", {"bar": False, "foo": False}),
        ("!bar? ( !foo )", {"bar": False, "foo": True}),
    ),
)
def test_condition(required_use, exclude):
    required_use = parse(required_use=required_use)
    solutions = tuple(solver(required_use, {"bar", "foo"}))
    assert len(solutions) == 3
    assert exclude not in solutions


@pytest.mark.parametrize(
    ("required_use", "exclude"),
    (
        ("?? ( bar foo )", {"bar": True, "foo": True}),
        ("?? ( !bar foo )", {"bar": False, "foo": True}),
        ("?? ( bar !foo )", {"bar": True, "foo": False}),
        ("?? ( !bar !foo )", {"bar": False, "foo": False}),
    ),
)
def test_at_most(required_use, exclude):
    required_use = parse(required_use=required_use)
    solutions = tuple(solver(required_use, {"bar", "foo"}))
    assert len(solutions) == 3
    assert exclude not in solutions


@pytest.mark.parametrize(
    ("required_use", "exclude"),
    (
        ("|| ( bar foo )", {"bar": False, "foo": False}),
        ("|| ( !bar foo )", {"bar": True, "foo": False}),
        ("|| ( bar !foo )", {"bar": False, "foo": True}),
        ("|| ( !bar !foo )", {"bar": True, "foo": True}),
    ),
)
def test_or(required_use, exclude):
    required_use = parse(required_use=required_use)
    solutions = tuple(solver(required_use, {"bar", "foo"}))
    assert len(solutions) == 3
    assert exclude not in solutions


@pytest.mark.parametrize(
    ("required_use", "include"),
    (
        ("bar foo", {"bar": True, "foo": True}),
        ("!bar foo", {"bar": False, "foo": True}),
        ("bar !foo", {"bar": True, "foo": False}),
        ("!bar !foo", {"bar": False, "foo": False}),
    ),
)
def test_and(required_use, include):
    required_use = parse(required_use=required_use)
    solutions = tuple(solver(required_use, {"bar", "foo"}))
    assert solutions == (include,)


@pytest.mark.parametrize(
    ("required_use", "iuse", "force_true"),
    (
        pytest.param(
            "test? ( jpeg jpeg2k tiff truetype )",
            {
                "examples",
                "imagequant",
                "jpeg",
                "jpeg2k",
                "lcms",
                "test",
                "tiff",
                "tk",
                "truetype",
                "webp",
                "xcb",
                "zlib",
            },
            {"test"},
            id="pillow",
        ),
        pytest.param(
            "test? ( cuda gpl? ( openssl? ( bindist ) fdk? ( bindist ) ) ) cuda? ( nvenc ) ^^ ( openssl fdk )",
            {"cuda", "gpl", "openssl", "bindist", "fdk", "test", "nvenc"},
            {"test", "fdk"},
            id="ffmpeg",
        ),
        pytest.param(
            "|| ( openssl ( gnutls ssl ) ) ssl? ( ( gnutls openssl ) )",
            {"openssl", "gnutls", "ssl"},
            {"ssl"},
            id="weird",
        ),
        pytest.param(
            "|| ( ssl ( gnutls? ( openssl ) ) )",
            {"openssl", "gnutls", "ssl"},
            {"gnutls"},
            id="weird2",
        ),
    ),
)
def test_complex_force_true(required_use, iuse, force_true):
    required_use = parse(required_use=required_use)
    solution = None
    for solution in islice(solver(required_use, iuse, force_true=force_true), 20):
        assert all(solution[flag] for flag in force_true)
        use_flags = tuple(k for k, v in solution.items() if v)
        misses = [
            restrict
            for restrict in required_use.evaluate_depset(use_flags)
            if not restrict.match(use_flags)
        ]
        assert not misses
    assert solution is not None


@pytest.mark.parametrize(
    ("required_use", "iuse", "force_false"),
    (
        pytest.param(
            "|| ( openssl ( gnutls ssl ) )",
            {"openssl", "gnutls", "ssl"},
            {"openssl"},
            id="custom",
        ),
    ),
)
def test_complex_force_false(required_use, iuse, force_false):
    required_use = parse(required_use=required_use)
    solution = None
    for solution in islice(solver(required_use, iuse, force_false=force_false), 20):
        assert all(not solution[flag] for flag in force_false)
        use_flags = tuple(k for k, v in solution.items() if v)
        misses = [
            restrict
            for restrict in required_use.evaluate_depset(use_flags)
            if not restrict.match(use_flags)
        ]
        assert not misses
    assert solution is not None
