# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

import pytest

from pkgcore.repository.util import SimpleTree
from pkgcore.scripts import pmerge
from pkgcore.util.parserestrict import parse_match


# TODO: make repo objs into configurable fixtures
class TestTargetParsing(object):

    def test_base_targets(self):
        repo = SimpleTree({'spork': {'foon': ('1', '1.0.1', '2')}})
        installed_repos = SimpleTree({'foo': {'bar': ('1')}})
        for cat in ('', 'spork/'):
            a = pmerge.parse_target(parse_match(f'={cat}foon-1'), repo, installed_repos)
            assert len(a) == 1
            assert a[0].key == 'spork/foon'
            assert [x.fullver for x in repo.itermatch(a[0])] == ['1']
            a = pmerge.parse_target(parse_match(f'{cat}foon'), repo, installed_repos)
            assert len(a) == 1
            assert a[0].key == 'spork/foon'
            assert (
                sorted(x.fullver for x in repo.itermatch(a[0])) ==
                sorted(['1', '1.0.1', '2'])
            )

    def test_no_matches(self):
        repo = SimpleTree({
            'spork': {'foon': ('1',)},
            'spork2': {'foon': ('2',)}})
        installed_repos = SimpleTree({'foo': {'bar': ('1')}})
        with pytest.raises(pmerge.NoMatches):
            pmerge.parse_target(parse_match("foo"), repo, installed_repos)

    def test_ambiguous(self):
        repo = SimpleTree({
            'spork': {'foon': ('1',)},
            'spork2': {'foon': ('2',)}})
        installed_repos = SimpleTree({'foo': {'bar': ('1')}})
        with pytest.raises(pmerge.AmbiguousQuery):
            pmerge.parse_target(parse_match("foon"), repo, installed_repos)

    def test_globbing(self):
        repo = SimpleTree({
            'spork': {'foon': ('1',)},
            'spork2': {'foon': ('2',)}})
        installed_repos = SimpleTree({'foo': {'bar': ('1')}})
        a = pmerge.parse_target(parse_match('*/foon'), repo, installed_repos)
        assert len(a) == 2

    def test_collisions_repo(self):
        # test pkg name collisions between real and virtual pkgs in a repo, but not installed
        # repos, the real pkg will be selected over the virtual
        installed_repos = SimpleTree({'foo': {'baz': ('1')}})
        repo = SimpleTree({'foo': {'bar': ('1',)}, 'virtual': {'bar': ('1',)}})
        a = pmerge.parse_target(parse_match("bar"), repo, installed_repos)
        assert len(a) == 1
        assert a[0].key == 'foo/bar'
        assert isinstance(a[0].key, str)

    def test_collisions_livefs(self):
        # test pkg name collisions between real and virtual pkgs on livefs
        # repos, the real pkg will be selected over the virtual
        installed_repos = SimpleTree({'foo': {'bar': ('1')}, 'virtual': {'bar': ('0')}})
        repo = SimpleTree({'foo': {'bar': ('1',)}, 'virtual': {'bar': ('1',)}})
        a = pmerge.parse_target(parse_match("bar"), repo, installed_repos)
        assert len(a) == 1
        assert a[0].key == 'foo/bar'
        assert isinstance(a[0].key, str)

    # TODO: add slotted (extra restrictions) collision test
