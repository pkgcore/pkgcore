# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

# TODO: move exceptions elsewhere, bind them to a base exception for pkgcore

import logging
from pkgcore.restrictions import packages, boolean
from pkgcore.util.lists import unique, flatten
from pkgcore.util.strings import iter_tokens

def conditional_converter(node, payload):
	if node[0] == "!":
		return packages.Conditional(node[1:], payload, negate=True)
	return packages.Conditional(node, payload)


class DepSet(boolean.AndRestriction):
	__slots__ = ("has_conditionals", "conditional_class", "node_conds") + boolean.AndRestriction.__slots__

	def __init__(self, dep_str, element_func, operators={"||":packages.OrRestriction,"":packages.AndRestriction}, \
		conditional_converter=conditional_converter, conditional_class=packages.Conditional, empty=False):

		"""dep_str is a dep style syntax, element_func is a callable returning the obj for each element, and
		cleanse_string controls whether or translation of tabs/newlines is required"""

		boolean.AndRestriction.__init__(self, packages.package_type)

		self.conditional_class = conditional_class
		self.node_conds = {}

		if empty:
			return

		# anyone who uses this routine as fodder for pushing a rewrite in lisp I reserve the right to deliver an
		# atomic wedgie upon.
		# ~harring

		conditionals, depsets = [], [self]
		raw_conditionals = []
		words = iter_tokens(dep_str, splitter=" \t\n")
		try:
			for k in words:
				if k == ")":
					# no elements == error.  if closures don't map up, indexerror would be chucked from trying to pop the frame
					# so that is addressed.
					if not depsets[-1].restrictions:
						raise ParseError(dep_str)
					elif conditionals[-1].endswith('?'):
						cond = raw_conditionals[:]
						depsets[-2].restrictions.append(conditional_converter(conditionals.pop(-1)[:-1], depsets[-1].restrictions))
						raw_conditionals.pop(-1)
						for x in depsets[-1]:
							self.node_conds.setdefault(x, []).append(cond)
					else:
						depsets[-2].restrictions.append(operators[conditionals.pop(-1)](*depsets[-1].restrictions))

					depsets.pop(-1)

				elif k.endswith('?') or k in operators or k=="(":
					if k != "(":
						# use conditional or custom op. no tokens left == bad dep_str.
						try:							k2 = words.next()
						except StopIteration:	k2 = ''

						if k2 != "(":
							raise ParseError(dep_str)
					else:
						# Unconditional subset - useful in the || ( ( a b ) c ) case
						k = ""

					# push another frame on
					depsets.append(self.__class__(dep_str, element_func, empty=True, conditional_converter=conditional_converter,
						conditional_class=self.conditional_class))

					conditionals.append(k)
					if k.endswith("?"):
						raw_conditionals.append(k[:-1])

				else:
					# node/element.
					depsets[-1].restrictions.append(element_func(k))


		except IndexError:
			# [][-1] for a frame access, which means it was a parse error.
			raise ParseError(dep_str)

		# check if any closures required
		if len(depsets) != 1:
			raise ParseError(dep_str)
		for x in self.node_conds:
			self.node_conds[x] = tuple(unique(flatten(self.node_conds[x])))

	def evaluate_depset(self, cond_dict):
		"""passed in a depset, does lookups of the node in cond_dict.
		no entry in cond_dict == conditional is off, else the bool value of the key's val in cond_dict"""

		if not self.has_conditionals:
			return self

		flat_deps = self.__class__("", str)

		stack = [self.restrictions]
		while stack:
			for node in stack[0]:
				if isinstance(node, self.conditional_class):
					if node.cond in cond_dict:
						if not node.negate:
							stack.append(node.restrictions)
					elif node.negate:
						stack.append(node.restrictions)
				else:
					# XXX: OrRestrictioins seem to fall in here...
					# Does "|| ( foo? ( bar ) baz )" work?
					# -- jstubbs
					flat_deps.restrictions.append(node)
			stack.pop(0)
		return flat_deps

	@property
	def has_conditionals(self):
		return len(self.node_conds) > 0

	def match(self, *a):
		raise NotImplementedError

	force_False = force_True = match

	def __str__(self):
		return ' '.join(str(x) for x in self.restrictions)

	def __iter__(self):
		return iter(self.restrictions)

def split_atom_depset_by_blockers(ds):
	"""returns a two depsets, (blockers, nonblockers)"""
	ccls = ds.conditional_class
	block = ds.__class__("", str, conditional_class=ccls)
	nonblock = ds.__class__("", str, conditional_class=ccls)
	if not ds.has_conditionals:
		block.restrictions = [x for x in ds if x.blocks]
		nonblock.restrictions = [x for x in ds if not x.blocks]
		return block, nonblock

	nbstack = [nonblock]
	bstack = [block]
	stack = [iter(ds)]
	nbconds, bconds = {}, {}

	conds = []
	while stack:
		reset = False
		for node in stack[-1]:
			if isinstance(node, ccls):
				stack.append(iter(node.restrictions))
				nbstack.append(node.clone_empty())
				bstack.append(node.clone_empty())
				conds.append(node.cond)
				reset = True
				break
			elif node.blocks:
				bstack[-1].restrictions.append(node)
			else:
				nbstack[-1].restrictions.append(node)
		if not reset:
			if len(stack) > 1:
				for s, d in ((nbstack, nbconds), (bstack, bconds)):
					if s[-1].restrictions:
						if conds[-1] is not None:
							d.setdefault(conds[-1], []).append(s[-1].restrictions)
						s[-2].restrictions.append(s[-1])
					s.pop(-1)
				conds.pop(-1)
			stack.pop(-1)

	# rebuild node_conds.
	for s, d in ((block, bconds), (nonblock, nbconds)):
		s.node_conds.update((x, tuple(unique(flatten(d[x])))) for x in d)

	return block, nonblock

class ParseError(Exception):

	def __init__(self, s):	
		self.dep_str = s

	def __str__(self):
		return "%s is unparseable" % self.dep_str
