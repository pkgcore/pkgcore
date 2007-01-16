# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


import operator

from pkgcore.test import TestCase

from pkgcore.cache import template, errors


class DictCache(template.database):

    """Minimal dict-backed cache for testing."""

    autocommits = True
    cleanse_keys = True

    def __init__(self, *args, **kwargs):
        template.database.__init__(self, *args, **kwargs)
        self.data = {}

    def _getitem(self, cpv):
        return self.data[cpv]

    def _setitem(self, cpv, values):
        self.data[cpv] = values

    def _delitem(self, cpv):
        del self.data[cpv]

    def __contains__(self, cpv):
        return cpv in self.data

    def iterkeys(self):
        return self.data.iterkeys()


class TemplateTest(TestCase):

    cache_keys = ("foo", "_eclasses_")

    def get_db(self, label='foo', readonly=False):
        return DictCache('nowhere', 'dictcache', self.cache_keys,
            readonly=readonly)

    def test_basics(self):
        self.cache = self.get_db()
        self.cache['spork'] = {'foo':'bar'}
        self.assertEquals({'foo': 'bar'}, self.cache['spork'])
        self.assertRaises(KeyError, operator.getitem, self.cache, 'notaspork')

        self.cache['spork'] = {'foo': 42}
        self.cache['foon'] = {'foo': 42}
        self.assertEquals({'foo': 42}, self.cache['spork'])
        self.assertEquals({'foo': 42}, self.cache['foon'])

        self.assertEquals(['foon', 'spork'], sorted(self.cache.keys()))
        self.assertEquals([('foon', {'foo': 42}), ('spork', {'foo': 42})],
                          sorted(self.cache.items()))
        del self.cache['foon']
        self.assertRaises(KeyError, operator.getitem, self.cache, 'foon')

        self.assertTrue(self.cache.has_key('spork'))
        self.assertFalse(self.cache.has_key('foon'))

        self.cache['empty'] = {'foo': ''}
        self.assertEquals({}, self.cache['empty'])

    def test_eclasses(self):
        self.cache = self.get_db()
        self.cache['spork'] = {'foo':'bar'}
        self.cache['spork'] = {'_eclasses_': {'spork': 'here',
                                              'foon': 'there'}}
        self.assertRaises(errors.CacheCorruption,
                          operator.getitem, self.cache, 'spork')

        self.cache['spork'] = {'_eclasses_': {'spork': ('here', 1),
                                              'foon': ('there', 2)}}
        self.assertIn(self.cache.data['spork']['_eclasses_'], [
                'spork\there\t1\tfoon\tthere\t2',
                'foon\tthere\t2\tspork\there\t1'])
        self.assertEquals({'spork': ('here', 1), 'foon': ('there', 2)},
                          self.cache['spork']['_eclasses_'])

    def test_readonly(self):
        self.cache = self.get_db()
        self.cache['spork'] = {'foo':'bar'}
        cache = self.get_db('rodictcache', True)
        cache.data = self.cache.data
        self.assertRaises(errors.ReadOnly,
                          operator.delitem, cache, 'spork')
        self.assertRaises(errors.ReadOnly,
                          operator.setitem, cache, 'spork', {'foo': 42})
        self.assertEquals({'foo': 'bar'}, cache['spork'])

#
# XXX: disabled by harring; get_matches is old code, still semi-working,
# but not even remotely part of the cache interface- that code needs to be
# gutted/refactored, with the majority of it happening higher up;
#
# reiterating; these tests should not be enabled till restriction translation
# is implemented, likely invalidating this code.
#
#    def test_get_matches(self):
#        self.db = self.get_db()
#        self.assertRaises(errors.InvalidRestriction,
#                          list, self.cache.get_matches({'foo': '*'}))
#        self.assertRaises(errors.InvalidRestriction,
#                          list, self.cache.get_matches({'bar': '.*'}))
#
#        self.cache['foon'] = {'foo': 'baz'}
#
#        self.assertEquals(['spork'],
#                          list(self.cache.get_matches({'foo': 'bar'})))
#        self.assertEquals(['foon', 'spork'],
#                          sorted(self.cache.get_matches({'foo': 'ba.'})))
#        self.assertEquals(['foon', 'spork'],
#                          sorted(self.cache.get_matches({})))
#
#        self.assertEquals(['spork'],
#                          list(self.cache.get_matches({'foo': ('BAR', re.I)})))
