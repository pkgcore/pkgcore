# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2


import operator
from pkgcore.test import TestCase
from pkgcore.cache import base, errors, bulk
from snakeoil.chksum import LazilyHashedPath


def _mk_chf_obj(**kwargs):
    kwargs.setdefault('mtime', 100)
    return LazilyHashedPath('/nonexistent/path', **kwargs)
_chf_obj = _mk_chf_obj()


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

    def __getitem__(self, cpv):
        # Protected dict's come back by default, but are a minor
        # pita to deal with for this code- thus we convert back.
        # Additionally, we drop any chksum info in the process.
        d = dict(base.__getitem__(self, cpv).iteritems())
        d.pop('_%s_' % self.chf_type, None)
        return d

    def __setitem__(self, cpv, data):
        data['_chf_'] = _chf_obj
        return base.__setitem__(self, cpv, data)

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

    def __getitem__(self, cpv):
        d = bulk.__getitem__(self, cpv)
        d.pop('_%s_' % self.chf_type, None)
        return d

    def __setitem__(self, cpv, data):
        data['_chf_'] = _chf_obj
        return bulk.__setitem__(self, cpv, data)


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
        self.cache['spork'] = {'_eclasses_': {'spork': _chf_obj,
                                              'foon': _chf_obj}}
        self.assertRaises(errors.CacheCorruption,
                          operator.getitem, self.cache, 'spork')

        self.cache['spork'] = {'_eclasses_': {'spork': _mk_chf_obj(mtime=1),
                                              'foon': _mk_chf_obj(mtime=2)}}
        self.assertIn(self.cache._data['spork']['_eclasses_'], [
                'spork\t1\tfoon\t2',
                'foon\t2\tspork\t1'])
        self.assertEqual(
            sorted([('foon', (('mtime', 2L),)), ('spork', (('mtime', 1L),))]),
            sorted(self.cache['spork']['_eclasses_']))

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
