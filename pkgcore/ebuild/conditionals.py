# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

# TODO: move exceptions elsewhere, bind them to a base exception for pkgcore

from pkgcore.restrictions import packages, values, boolean
from pkgcore.util.lists import unique, flatten
from pkgcore.util.strings import iter_tokens

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
	

class DepSet(object):
	__slots__ = ("has_conditionals", "element_class", "node_conds", "restrictions")

	def __init__(self, dep_str, element_class, operators={"||":packages.OrRestriction,"":packages.AndRestriction}):

		"""dep_str is a dep style syntax, element_func is a callable returning the obj for each element, and
		cleanse_string controls whether or translation of tabs/newlines is required"""

		self.node_conds = {}
		self.restrictions = []
		self.element_class = element_class
		
		raw_conditionals = []
		depsets = [self.restrictions]
		use_asserts = []
		
		words = iter_tokens(dep_str, splitter=" \t\n")
		try:
			for k in words:
				if k == ")":
					# no elements == error.  if closures don't map up, indexerror would be chucked from trying to pop the frame
					# so that is addressed.
					if not depsets[-1]:
						raise ParseError(dep_str)
					elif raw_conditionals[-1].endswith('?'):
						for x in (y for y in depsets[-1] if not isinstance(y, packages.Conditional)):
							self.node_conds.setdefault(x, []).append(use_asserts[-1])

						c = convert_use_reqs((raw_conditionals[-1][:-1],))

						depsets[-2].append(packages.Conditional("use", c, tuple(depsets[-1])))
						use_asserts.pop(-1)
					else:
						depsets[-2].append(operators[raw_conditionals[-1]](finalize=True, *depsets[-1]))
					
					raw_conditionals.pop(-1)
					depsets.pop(-1)

				elif k.endswith('?') or k in operators or k=="(":
					if k != "(":
						# use conditional or custom op. no tokens left == bad dep_str.
						try:
							k2 = words.next()
						except StopIteration:
							k2 = ''

						if k2 != "(":
							raise ParseError(dep_str)

					else:
						# Unconditional subset - useful in the || ( ( a b ) c ) case
						k = ""

					# push another frame on
					depsets.append([])
					raw_conditionals.append(k)
					if k.endswith("?"):
						use_asserts.append(convert_use_reqs([x[:-1] for x in raw_conditionals if x.endswith("?")]))

				else:
					# node/element.
					depsets[-1].append(element_class(k))


		except IndexError:
			# [][-1] for a frame access, which means it was a parse error.
			raise
			raise ParseError(dep_str)

		# check if any closures required
		if len(depsets) != 1:
			raise ParseError(dep_str)
		self.restrictions = tuple(self.restrictions)

	def evaluate_depset(self, cond_dict):
		"""passed in a depset, does lookups of the node in cond_dict.
		no entry in cond_dict == conditional is off, else the bool value of the key's val in cond_dict"""

		if not self.has_conditionals:
			return self

		flat_deps = self.__class__("", str)

		stack = [packages.AndRestriction, iter(self.restrictions)]
		base_restrict = []
		restricts = [base_restrict]
#		import pdb;pdb.set_trace()
		while len(stack) > 1:
			exhausted = True
			for node in stack[-1]:
				if isinstance(node, self.element_class):
					restricts[-1].append(node)
					continue
				if isinstance(node, packages.Conditional):
					if not (node.restriction.match(cond_dict) and node.payload):
						continue
					stack.append(packages.AndRestriction)
					stack.append(iter(node.payload))
				else:
					stack.append(node.change_restrictions)
					stack.append(iter(node.restrictions))
				restricts.append([])
				exhausted = False
				break

			if exhausted:
				stack.pop(-1)
				if len(restricts) != 1:
					if restricts[-1]:
						# optimization to avoid uneccessary frames.
						if len(restricts[-1]) == 1:
							restricts[-2].append(restricts[-1][0])
						elif stack[-1] is stack[-3] is packages.AndRestriction:
							restricts[-2].extend(restricts[-1])
						else:
							restricts[-2].append(stack[-1](*restricts[-1]))
					stack.pop(-1)
				restricts.pop(-1)

		flat_deps.restrictions = tuple(base_restrict)
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

	def __getitem__(self, key):
		return self.restrictions[key]


class ParseError(Exception):

	def __init__(self, s):	
		self.dep_str = s

	def __str__(self):
		return "%s is unparseable" % self.dep_str
