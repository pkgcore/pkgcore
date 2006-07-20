# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
DepSet parsing (depends, rdepends, SRC_URI, license, etc) generating appropriate conditionals
"""

# TODO: move exceptions elsewhere, bind them to a base exception for pkgcore

from pkgcore.restrictions import packages, values, boolean
from pkgcore.util.iterables import expandable_chain
from pkgcore.package.atom import atom

def convert_use_reqs(uses):
	assert len(uses)
	use_asserts = tuple(x for x in uses if x[0] != "!")
	if len(use_asserts) != len(uses):
		use_negates = values.ContainmentMatch(all=True, negate=True, *tuple(x[1:] for x in uses if x[0] == "!"))
		assert len(use_negates.vals)
		if not use_asserts:
			return use_negates
	else:
		return values.ContainmentMatch(all=True, *use_asserts)
	return values.AndRestriction(values.ContainmentMatch(all=True, *use_asserts), use_negates)


class DepSet(boolean.AndRestriction):
	
	"""
	gentoo DepSet syntax parser
	"""

	__slots__ = ("has_conditionals", "element_class", "_node_conds", "restrictions")
	type = packages.package_type
	negate = False

	def __init__(self, dep_str, element_class, \
		operators={"||":packages.OrRestriction,"":packages.AndRestriction}, 
		element_func=None):

		"""
		@param dep_str: string abiding by DepSet syntax
		@param operators: mapping of node -> callable for special operators in DepSet syntax
		@param element_func: if None, element_class is used for generating elements, else it's used to generate elements.
		Mainly useful for when you need to curry a few args for instance generation, since element_class _must_ be a class
		@param element_class: class of generated elements
		"""

		self.restrictions = []
		self.element_class = element_class
		if element_func is None:
			element_func = element_class
		self._node_conds = False

		raw_conditionals = []
		depsets = [self.restrictions]

		words = iter(dep_str.split())
		try:
			for k in words:
				if k == ")":
					# no elements == error.  if closures don't map up, indexerror would be chucked from trying to pop the frame
					# so that is addressed.
					if not depsets[-1]:
						raise ParseError(dep_str)
					elif raw_conditionals[-1].endswith('?'):
						self._node_conds = True

						c = convert_use_reqs((raw_conditionals[-1][:-1],))

						depsets[-2].append(packages.Conditional("use", c, tuple(depsets[-1])))
					else:
						depsets[-2].append(operators[raw_conditionals[-1]](finalize=True, *depsets[-1]))

					raw_conditionals.pop(-1)
					depsets.pop(-1)

				elif k.endswith('?') or k in operators or k == "(":
					if k != "(":
						# use conditional or custom op. no tokens left == bad dep_str.
						try:
							k2 = words.next()
						except StopIteration:
							k2 = ''

						if k2 != "(":
							raise ParseError(dep_str, k2)

					else:
						# Unconditional subset - useful in the || ( ( a b ) c ) case
						k = ""

					# push another frame on
					depsets.append([])
					raw_conditionals.append(k)

				elif "(" in k or ")" in k or "|" in k:
					raise ParseError(dep_str, k)
				else:
					# node/element.
					depsets[-1].append(element_func(k))


		except IndexError:
			# [][-1] for a frame access, which means it was a parse error.
			raise
			raise ParseError(dep_str)

		# check if any closures required
		if len(depsets) != 1:
			raise ParseError(dep_str)
		self.restrictions = tuple(self.restrictions)


	def evaluate_depset(self, cond_dict, tristate_filter=None):
		"""
		@param cond_dict: container to be used for conditional collapsing, typically is a use list
		@param tristate_filter: a control; if specified, must be a container of conditionals to lock to cond_dict.
		during processing, if it's not in tristate_filter will automatically enable the payload
		(regardless of the conditionals negation)
		"""

		if not self.has_conditionals:
			return self

		flat_deps = self.__class__("", str)

		stack = [packages.AndRestriction, iter(self.restrictions)]
		base_restrict = []
		restricts = [base_restrict]
		count = 1
		while count:
			for node in stack[-1]:
				if isinstance(node, self.element_class):
					restricts[-1].append(node)
					continue
				if isinstance(node, packages.Conditional):
					if not node.payload:
						continue
					elif tristate_filter is not None:
						assert len(node.restriction.vals) == 1
						val = list(node.restriction.vals)[0]
						if val in tristate_filter:
							# if val is forced true, but the check is negation ignore it
							# if !mips != mips
							if (val in cond_dict) == node.restriction.negate:
								continue
					elif not node.restriction.match(cond_dict):
						continue
					stack += [packages.AndRestriction, iter(node.payload)]
				else:
					stack += [node.change_restrictions, iter(node.restrictions)]
				count += 1
				restricts.append([])
				break
			else:
				stack.pop(-1)
				l = len(restricts)
				if l != 1:
					if restricts[-1]:
						# optimization to avoid uneccessary frames.
						if l == 1:
							restricts[-2].append(restricts[-1][0])
						elif stack[-1] is stack[-3] is packages.AndRestriction:
							restricts[-2].extend(restricts[-1])
						else:
							restricts[-2].append(stack[-1](*restricts[-1]))
					stack.pop(-1)
				count -= 1
				restricts.pop(-1)

		flat_deps.restrictions = tuple(base_restrict)
		return flat_deps

	@staticmethod
	def find_cond_nodes(restriction_set):
		conditions_stack = []
		new_set = expandable_chain(restriction_set)
		for cur_node in new_set:
			if isinstance(cur_node, packages.Conditional):
				conditions_stack.append(cur_node.restriction)
				new_set.appendleft(list(cur_node.payload) + [None])
			elif isinstance(cur_node, boolean.base) and not isinstance(cur_node, atom):
				new_set.appendleft(cur_node.restrictions)
			elif cur_node is None:
				conditions_stack.pop()
			else: # leaf
				yield (cur_node, conditions_stack[:])

	@property
	def node_conds(self):
		if self._node_conds is False:
			self._node_conds = {}
		elif self._node_conds is True:
			nc = {}

			found_conds = self.find_cond_nodes(self.restrictions)

			always_required = set()

			for payload, restrictions in found_conds:
				if not restrictions:
					always_required.add(payload)
				else:
					if len(restrictions) == 1:
						current = restrictions[0]
					else:
						current = values.AndRestriction(all=True, finalize=True, *restrictions)

					nc.setdefault(payload, []).append(current)

			for k in always_required:
				if k in nc:
					del nc[k]
			for k in nc:
				nc[k] = tuple(nc[k])

			self._node_conds = nc

		return self._node_conds

	@property
	def has_conditionals(self):
		return bool(self._node_conds)

	def match(self, *a):
		raise NotImplementedError

	force_False = force_True = match

	def __str__(self):
		return ' '.join(self._stringify_node(x) for x in self.restrictions)

	def __iter__(self):
		return iter(self.restrictions)

	def __getitem__(self, key):
		return self.restrictions[key]

	def _stringify_node(self, node):
		if isinstance(node, boolean.OrRestriction):
			return "|| ( %s )" % " ".join(self._stringify_node(x) for x in node.restrictions)
		elif isinstance(node, packages.Conditional):
			assert len(node.restriction.vals) == 1
			return "%s%s? ( %s )" % (node.negate and "!" or "", list(node.restriction.vals)[0], \
				" ".join(self._stringify_node(x) for x in node.payload))

		return str(node)
		

class ParseError(Exception):

	def __init__(self, s, token=None):
		self.dep_str, self.token = s, token

	def __str__(self):
		if self.token is not None:
			return "%s is unparesable\nflagged token- %s" % (repr(self.dep_str), repr(self.token))
		else:
			return "%s is unparseable" % repr(self.dep_str)
