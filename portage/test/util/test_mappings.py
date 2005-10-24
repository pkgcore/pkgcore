# Copyright: 2005 Gentoo Foundation
# Author(s): Marien Zwart <m_zwart@123mail.org>
# License: GPL2
# $Id:$


from twisted.trial import unittest

from portage.util import mappings


def a_dozen():
	return range(12)


class RememberingNegateMixin(object):

	def setUpRememberingNegate(self):
		self.negateCalls = []
		def negate(i):
			self.negateCalls.append(i)
			return -i
		self.negate = negate

	def tearDownRememberingNegate(self):
		del self.negate
		del self.negateCalls
		
		
class IndexableSequenceTest(unittest.TestCase):

	def setUp(self):
		self.negateCalls = []
		def negTuple(key):
			"""returns (-key, key) for 1 <= key <= 11, () for key == 0."""
			# this is screwy: we need to raise here or the seq will
			# think we have this key even if it is not in a_dozen
			self.negateCalls.append(key)
			if 0 <= key <= 11:
				if key:
					return -key, key
				else:
					return ()
			else:
				raise KeyError(key)
		def checkKeyVal(key, val):
			self.assertEquals(abs(val), key)
			return val
		self.seq = mappings.IndexableSequence(
			a_dozen, negTuple, returnIterFunc=checkKeyVal)

	def tearDown(self):
		del self.negateCalls

	def preTest(self):
		"""pre-test setup that is part of the test."""

	def postTest(self):
		"""final checks, part of the test."""
		
	def test_contains(self):
		self.preTest()
		self.failIf(13 in self.seq)
		self.failUnless(7 in self.seq)
		self.postTest()

	def test_getitem(self):
		self.preTest()
		self.assertEquals(self.seq[3], (-3, 3))
		initialLen = len(self.negateCalls)
		# should be cached
		self.assertEquals(self.seq[3], (-3, 3))
		self.assertEquals(initialLen, len(self.negateCalls))
		self.postTest()

	def test_keys(self):
		self.preTest()
		self.assertEquals(sorted(self.seq.keys()), range(12))
		self.postTest()

	def test_items(self):
		self.preTest()
		self.assertEquals(
			sorted(self.seq.items()),
            [(0, ())] + [(i, (-i, i)) for i in range(1, 12)])
		self.postTest()

	def test_sequencelike(self):
		self.preTest()
		self.assertEquals(
            range(-11, 0) + range(1, 12), sorted(list(self.seq)))
		self.assertEquals(22, len(self.seq))
		self.postTest()


class IndexableSequenceFullyCachedTest(IndexableSequenceTest):

	def preTest(self):
		# fill the cache
		self.seq.items()
		self.finalLen = len(self.negateCalls)
	
	def postTest(self):
		self.assertEquals(self.finalLen, len(self.negateCalls))


class IndexableSequencePartiallyCachedTest(IndexableSequenceTest):

	def preTest(self):
		# pull in some items
		self.seq[3]
		self.seq[5]


class IndexableSequenceSpecialCasesTest(unittest.TestCase):

	def test_default_returnIterFunc(self):
		def keys():
			return 'a', 'b'
		def values(key):
			return 'c', 'd'
		seq = mappings.IndexableSequence(keys, values)
		self.assertEquals(sorted(list(seq)), ['a/c', 'a/d', 'b/c', 'b/d'])

	def test_returnEmpty(self):
		def keys():
			return False, True
		def values(key):
			if key:
				return 1, 2
			else:
				return ()
		def glue(key, val):
			return key, val
		seq = mappings.IndexableSequence(
			keys, values, returnEmpty=True, returnIterFunc=glue)
		self.assertEquals(3, len(seq))
		self.assertEquals([False, (True, 1), (True, 2)], sorted(list(seq)))

class LazyValDictTestMixin(object):

	def test_invalid_operations(self):
		# we're not mutable
		def set(i, v):
			self.dict[i] = v
		def remove(i):
			del self.dict[i]
		self.assertRaises(AttributeError, set, 7, 7)
		self.assertRaises(AttributeError, remove, 7)

	def test_contains(self):
		self.failUnless(7 in self.dict)
		self.failIf(12 in self.dict)

	def test_keys(self):
		self.failUnlessEqual(sorted(self.dict.keys()), list(range(12)))

	def test_getkey(self):
		self.assertEquals(self.dict[3], -3)
		# missing key
		def get():
			return self.dict[42]
		self.assertRaises(KeyError, get)

	def test_caching(self):
		self.dict[11]
		self.dict[11]
		self.assertEquals(self.negateCalls, [11])
		

class LazyValDictWithListTest(
	unittest.TestCase, LazyValDictTestMixin, RememberingNegateMixin):
	
	def setUp(self):
		self.setUpRememberingNegate()
		self.dict = mappings.LazyValDict(range(12), self.negate)

	def tearDown(self):
		self.tearDownRememberingNegate()


class LazyValDictWithFuncTest(
	unittest.TestCase, LazyValDictTestMixin, RememberingNegateMixin):

	def setUp(self):
		self.setUpRememberingNegate()
		self.dict = mappings.LazyValDict(a_dozen, self.negate)

	def tearDown(self):
		self.tearDownRememberingNegate()
	

class LazyValDictTest(unittest.TestCase):

	def test_invalid_init_args(self):
		self.assertRaises(TypeError, mappings.LazyValDict, [1], 42)
		self.assertRaises(TypeError, mappings.LazyValDict, 42, a_dozen)
		

# TODO check for valid values for dict.new, since that seems to be
# part of the interface?
class ProtectedDictTest(unittest.TestCase):

	def setUp(self):
		self.orig = {1: -1, 2: -2}
		self.dict = mappings.ProtectedDict(self.orig)

	def test_basic_operations(self):
		self.assertEquals(self.dict[1], -1)
		def get(i):
			return self.dict[i]
		self.assertRaises(KeyError, get, 3)
		self.assertEquals(sorted(self.dict.keys()), [1, 2])
		self.failIf(-1 in self.dict)
		self.failUnless(2 in self.dict)
		def remove(i):
			del self.dict[i]
		self.assertRaises(KeyError, remove, 50)

	def test_basic_mutating(self):
		# add something
		self.dict[7] = -7
		def checkAfterAdding():
			self.assertEquals(self.dict[7], -7)
			self.failUnless(7 in self.dict)
			self.assertEquals(sorted(self.dict.keys()), [1, 2, 7])
		checkAfterAdding()
		# remove it again
		del self.dict[7]
		self.failIf(7 in self.dict)
		def get(i):
			return self.dict[i]
		self.assertRaises(KeyError, get, 7)
		self.assertEquals(sorted(self.dict.keys()), [1, 2])
		# add it back
		self.dict[7] = -7
		checkAfterAdding()
		# remove something not previously added
		del self.dict[1]
		self.failIf(1 in self.dict)
		self.assertRaises(KeyError, get, 1)
		self.assertEquals(sorted(self.dict.keys()), [2, 7])
		# and add it back
		self.dict[1] = -1
		checkAfterAdding()


class InvertedContainsTest(unittest.TestCase):

	def setUp(self):
		self.set = mappings.InvertedContains(range(12))
	
	def test_basic(self):
		self.failIf(7 in self.set)
		self.failUnless(-7 in self.set)


class LimitedChangeSetTest(unittest.TestCase):

	def setUp(self):
		self.set = mappings.LimitedChangeSet(range(12))

	def test_basic(self, changes=0):
		# this should be a no-op
		self.set.rollback(changes)
		# and this is invalid
		self.assertRaises(TypeError, self.set.rollback, changes + 1)
		self.failUnless(0 in self.set)
		self.failIf(12 in self.set)
		self.assertEquals(12, len(self.set))
		self.assertEquals(sorted(list(self.set)), list(range(12)))
		self.assertEquals(changes, self.set.changes_count())
		self.assertRaises(TypeError, self.set.rollback, -1)

	def test_dummy_commit(self):
		# this should be a no-op
		self.set.commit()
		# so this should should run just as before
		self.test_basic()

	def test_adding(self):
		self.set.add(13)
		self.failUnless(13 in self.set)
		self.assertEquals(13, len(self.set))
		self.assertEquals(sorted(list(self.set)), list(range(12)) + [13])
		self.assertEquals(1, self.set.changes_count())
		self.assertRaises(mappings.Unchangable, self.set.add, 13)
		self.assertRaises(mappings.Unchangable, self.set.remove, 13)

	def test_add_rollback(self):
		self.set.add(13)
		self.set.rollback(0)
		# this should run just as before
		self.test_basic()

	def test_add_commit_remove_commit(self):
		self.set.add(13)
		self.set.commit()
		# should look like right before commit
		self.assertEquals(13, len(self.set))
		self.assertEquals(sorted(list(self.set)), list(range(12)) + [13])
		self.assertEquals(0, self.set.changes_count())
		# and remove...
		self.set.remove(13)
		# should be back to basic, but with 1 change
		self.test_basic(1)
		self.set.commit()
		self.test_basic()

	def test_removing(self):
		self.set.remove(0)
		self.failIf(0 in self.set)
		self.assertEquals(11, len(self.set))
		self.assertEquals(sorted(list(self.set)), list(range(1, 12)))
		self.assertEquals(1, self.set.changes_count())
		self.assertRaises(mappings.Unchangable, self.set.add, 0)

	def test_remove_rollback(self):
		self.set.remove(0)
		self.set.rollback(0)
		self.test_basic()

	def test_remove_commit_add_commit(self):
		self.set.remove(0)
		self.set.commit()
		self.failIf(0 in self.set)
		self.assertEquals(11, len(self.set))
		self.assertEquals(sorted(list(self.set)), list(range(1, 12)))
		self.assertEquals(0, self.set.changes_count())
		self.set.add(0)
		self.test_basic(1)
		self.set.commit()
		self.test_basic()

	def test_longer_transaction(self):
		self.set.add(12)
		self.set.remove(7)
		self.set.rollback(1)
		self.set.add(-1)
		self.set.commit()
		self.assertEquals(sorted(list(self.set)), list(range(-1, 13)))

	def test_str(self):
		self.assertEquals(
			str(mappings.LimitedChangeSet([7])), 'LimitedChangeSet([7])')


class LimitedChangeSetWithBlacklistTest(unittest.TestCase):

    def setUp(self):
        self.set = mappings.LimitedChangeSet(range(12), [3, 13])

    def test_basic(self):
		self.failUnless(0 in self.set)
		self.failIf(12 in self.set)
		self.assertEquals(12, len(self.set))
		self.assertEquals(sorted(list(self.set)), list(range(12)))
		self.assertEquals(0, self.set.changes_count())
		self.assertRaises(TypeError, self.set.rollback, -1)

    def test_adding_blacklisted(self):
        self.assertRaises(mappings.Unchangable, self.set.add, 13)

    def test_removing_blacklisted(self):
        self.assertRaises(mappings.Unchangable, self.set.remove, 3)
		
class ImmutableDictTest(unittest.TestCase):

	def setUp(self):
		self.dict = mappings.ImmutableDict(**{1: -1, 2: -2})

	def test_invalid_operations(self):
		initialHash = hash(self.dict)
		def remove(k):
			del self.dict[k]
		def set(k, v):
			self.dict[k] = v
		self.assertRaises(TypeError, remove, 1)
		self.assertRaises(TypeError, remove, 7)
		self.assertRaises(TypeError, set, 1, -1)
		self.assertRaises(TypeError, set, 7, -7)
		self.assertRaises(TypeError, self.dict.clear)
		self.assertRaises(TypeError, self.dict.update, {6: -6})
		self.assertRaises(TypeError, self.dict.pop, 1)
		self.assertRaises(TypeError, self.dict.popitem)
		self.assertRaises(TypeError, self.dict.setdefault, 6, -6)
		self.assertEquals(initialHash, hash(self.dict))
