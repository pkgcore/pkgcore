# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2


import operator
from pkgcore.test import TestCase
from pkgcore.cache import base, errors, bulk


class DictCache(base):
    """Minimal dict-backed cache for testing."""

    cleanse_keys = True
    autocommits = True
    __has_working_commit__ = False

    def __init__(self, *args, **kwargs):
        base.__init__(self, *args, **kwargs)
        self._data = {}

    def _getitem(self, cpv):
        return self._data[cpv]

    def _setitem(self, cpv, values):
        self._data[cpv] = values

    def _delitem(self, cpv):
        del self._data[cpv]

    def __contains__(self, cpv):
        return cpv in self._data

    def iterkeys(self):
        return self._data.iterkeys()


class DictCacheBulk(bulk):

    cleanse_keys = True
    __has_working_commit__ = True

    def __init__(self, *args, **kwargs):
        bulk.__init__(self, *args, **kwargs)
        self._data = {}
        self._write_count = 0

    def _read_data(self):
        return self._data.copy()

    def _write_data(self):
        self._data = self.data.copy()
        self._write_count += 1


class BaseTest(TestCase):

    cache_keys = ("foo", "_eclasses_")

    def get_db(self, readonly=False):
        return DictCache(auxdbkeys=self.cache_keys,
            readonly=readonly)

    def test_basics(self):
        self.cache = self.get_db()
        self.cache['spork'] = {'foo':'bar'}
        self.assertEqual({'foo': 'bar'}, self.cache['spork'])
        self.assertRaises(KeyError, operator.getitem, self.cache, 'notaspork')

        self.cache['spork'] = {'foo': 42}
        self.cache['foon'] = {'foo': 42}
        self.assertEqual({'foo': 42}, self.cache['spork'])
        self.assertEqual({'foo': 42}, self.cache['foon'])

        self.assertEqual(['foon', 'spork'], sorted(self.cache.keys()))
        self.assertEqual([('foon', {'foo': 42}), ('spork', {'foo': 42})],
                          sorted(self.cache.items()))
        del self.cache['foon']
        self.assertRaises(KeyError, operator.getitem, self.cache, 'foon')

        self.assertTrue(self.cache.has_key('spork'))
        self.assertFalse(self.cache.has_key('foon'))

        self.cache['empty'] = {'foo': ''}
        self.assertEqual({}, self.cache['empty'])

    def test_eclasses(self):
        self.cache = self.get_db()
        self.cache['spork'] = {'foo':'bar'}
        self.cache['spork'] = {'_eclasses_': {'spork': 'here',
                                              'foon': 'there'}}
        self.assertRaises(errors.CacheCorruption,
                          operator.getitem, self.cache, 'spork')

        self.cache['spork'] = {'_eclasses_': {'spork': ('here', 1),
                                              'foon': ('there', 2)}}
        self.assertIn(self.cache._data['spork']['_eclasses_'], [
                'spork\there\t1\tfoon\tthere\t2',
                'foon\tthere\t2\tspork\there\t1'])
        self.assertEqual({'spork': ('here', 1), 'foon': ('there', 2)},
                          self.cache['spork']['_eclasses_'])

    def test_readonly(self):
        self.cache = self.get_db()
        self.cache['spork'] = {'foo':'bar'}
        cache = self.get_db(True)
        cache._data = self.cache._data
        self.assertRaises(errors.ReadOnly,
                          operator.delitem, cache, 'spork')
        self.assertRaises(errors.ReadOnly,
                          operator.setitem, cache, 'spork', {'foo': 42})
        self.assertEqual({'foo': 'bar'}, cache['spork'])

    def test_clear(self):
        cache = self.get_db()
        cache['spork'] = {'foo':'bar'}
        self.assertEqual({'foo':'bar'}, cache['spork'])
        self.assertEqual(list(cache), ['spork'])
        cache['dork'] = {'foo':'bar2'}
        cache['dork2'] = {'foo':'bar2'}
        self.assertEqual(list(sorted(cache)), sorted(['dork', 'dork2', 'spork']))
        cache.clear()
        self.assertEqual(list(cache), [])

    def test_sync_rate(self):
        db = self.get_db()
        tracker = []

        def commit(tracker=tracker, raw_commit=db.commit):
            tracker.append(True)
            if db.__has_working_commit__:
                raw_commit()

        db.commit = commit
        db.autocommits = False

        db.set_sync_rate(2)
        db["dar"] = {"foo":"blah"}
        self.assertFalse(tracker)
        db["dar2"] = {"foo":"blah"}
        self.assertLen(tracker, 1)
        self.assertEqual(sorted(db), ["dar", "dar2"])
        db["dar3"] = {"foo":"blah"}
        self.assertLen(tracker, 1)

        # finally ensure sync_rate(1) behaves
        db.set_sync_rate(1)
        # ensure it doesn't flush just for fiddling w/ sync rate
        self.assertLen(tracker, 1)
        db["dar4"] = {"foo":"blah"}
        self.assertLen(tracker, 2)
        db["dar5"] = {"foo":"blah"}
        self.assertLen(tracker, 3)


class TestBulk(BaseTest):

    def get_db(self, readonly=False):
        return DictCacheBulk(auxdbkeys=self.cache_keys,
            readonly=readonly)

    def test_filtering(self):
        db = self.get_db()
        # write a key outside of known keys
        db["dar"] = {"foo2":"dar"}
        self.assertEqual(db["dar"].items(), [])


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
#        self.assertEqual(['spork'],
#                          list(self.cache.get_matches({'foo': 'bar'})))
#        self.assertEqual(['foon', 'spork'],
#                          sorted(self.cache.get_matches({'foo': 'ba.'})))
#        self.assertEqual(['foon', 'spork'],
#                          sorted(self.cache.get_matches({})))
#
#        self.assertEqual(['spork'],
#                          list(self.cache.get_matches({'foo': ('BAR', re.I)})))
