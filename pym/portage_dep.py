# deps.py -- Portage dependency resolution functions
# Copyright 2003-2004 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header$
cvs_id_string="$Id: portage_dep.py 1773 2005-05-05 06:24:08Z jstubbs $"[5:-2]

# DEPEND SYNTAX:
#
# 'use?' only affects the immediately following word!
# Nesting is the only legal way to form multiple '[!]use?' requirements.
#
# Where: 'a' and 'b' are use flags, and 'z' is a depend atom.
#
# "a? z"	   -- If 'a' in [use], then b is valid.
# "a? ( z )"       -- Syntax with parenthesis.
# "a? b? z"	-- Deprecated.
# "a? ( b? z )"    -- Valid
# "a? ( b? ( z ) ) -- Valid
#

import os,string,types,sys,copy
import portage_exception
import portage_versions
import portage_syntax

OPERATORS="*<=>~!"
ENDVERSION_KEYS = ["pre", "p", "alpha", "beta", "rc"]

def dep_getcpv(s):
	return s.strip(OPERATORS)

def get_operator(mydep):
	"""
	returns '~', '=', '>', '<', '=*', '>=', or '<='
	"""

	if mydep[0] == "~":
		operator = "~"
	elif mydep[0] == "=":
		if mydep[-1] == "*":
			operator = "=*"
		else:
			operator = "="
	elif mydep[0] in "><":
		if len(mydep) > 1 and mydep[1] == "=":
			operator = mydep[0:2]
		else:
			operator = mydep[0]
	else:
		operator = None
	return operator

def isjustname(mypkg):
	myparts=mypkg.split('-')
	for x in myparts:
		if portage_versions.ververify(x):
			return 0
	return 1


def isvalidatom(atom):
	mycpv_cps = portage_versions.catpkgsplit(dep_getcpv(atom))
	operator = get_operator(atom)
	if operator:
		if mycpv_cps and mycpv_cps[0] != "null":
			# >=cat/pkg-1.0
			return 1
		else:
			# >=cat/pkg or >=pkg-1.0 (no category)
			return 0
	if mycpv_cps:
		# cat/pkg-1.0
		return 0
	if len(atom.split('/'))==2:
		# cat/pkg
		return 1
	else:
		return 0


def strip_empty(myarr):
	for x in range(len(myarr)-1, -1, -1):
		if not myarr[x]:
			del myarr[x]
	return myarr

def paren_reduce(mystr,tokenize=1):
	"Accepts a list of strings, and converts '(' and ')' surrounded items to sub-lists"
	mylist = []
	while mystr:
		if ("(" not in mystr) and (")" not in mystr):
			freesec = mystr
			subsec = None
			tail = ""
		elif mystr[0] == ")":
			return [mylist,mystr[1:]]
		elif ("(" in mystr) and (mystr.index("(") < mystr.index(")")):
			freesec,subsec = mystr.split("(",1)
			subsec,tail = paren_reduce(subsec,tokenize)
		else:
			subsec,tail = mystr.split(")",1)
			if tokenize:
				subsec = strip_empty(subsec.split(" "))
				return [mylist+subsec,tail]
			return [mylist+[subsec],tail]
		mystr = tail
		if freesec:
			if tokenize:
				mylist = mylist + strip_empty(freesec.split(" "))
			else:
				mylist = mylist + [freesec]
		if subsec is not None:
			mylist = mylist + [subsec]
	return mylist

def use_reduce(deparray, uselist=[], masklist=[], matchall=0, excludeall=[]):
	"""Takes a paren_reduce'd array and reduces the use? conditionals out
	leaving an array with subarrays
	"""
	# Quick validity checks
	for x in range(1,len(deparray)):
		if deparray[x] in ["||","&&"]:
			if len(deparray) == x:
				# Operator is the last element
				raise portage_exception.InvalidDependString("INVALID "+deparray[x]+" DEPEND STRING: "+str(deparray))
			if type(deparray[x+1]) != types.ListType:
				# Operator is not followed by a list
				raise portage_exception.InvalidDependString("INVALID "+deparray[x]+" DEPEND STRING: "+str(deparray))
	if deparray and deparray[-1] and deparray[-1][-1] == "?":
		# Conditional with no target
		raise portage_exception.InvalidDependString("INVALID "+deparray[x]+" DEPEND STRING: "+str(deparray))

	#XXX: Compatibility -- Still required?
	if ("*" in uselist):
		matchall=1

	mydeparray = deparray[:]
	rlist = []
	while mydeparray:
		head = mydeparray.pop(0)

		if type(head) == types.ListType:
			rlist = rlist + [use_reduce(head, uselist, masklist, matchall, excludeall)]

		else:
			if head[-1] == "?": # Use reduce next group on fail.
				# Pull any other use conditions and the following atom or list into a separate array
				newdeparray = [head]
				while isinstance(newdeparray[-1], str) and newdeparray[-1][-1] == "?":
					if mydeparray:
						newdeparray.append(mydeparray.pop(0))
					else:
						raise ValueError, "Conditional with no target."

				# Deprecation checks
				warned = 0
				if len(newdeparray[-1]) == 0:
					sys.stderr.write("Note: Empty target in string. (Deprecated)\n")
					warned = 1
				if len(newdeparray) != 2:
					sys.stderr.write("Note: Nested use flags without parenthesis (Deprecated)\n")
					warned = 1
				if warned:
					sys.stderr.write("  --> "+string.join(map(str,[head]+newdeparray))+"\n")

				# Check that each flag matches
				ismatch = True
				for head in newdeparray[:-1]:
					head = head[:-1]
					if head[0] == "!":
						head = head[1:]
						if not matchall and head in uselist or head in excludeall:
							ismatch = False
							break
					elif head not in masklist:
						if not matchall and head not in uselist:
							ismatch = False
							break
					else:
						ismatch = False

				# If they all match, process the target
				if ismatch:
					target = newdeparray[-1]
					if isinstance(target, list):
						rlist += [use_reduce(target, uselist, masklist, matchall, excludeall)]
					else:
						rlist += [target]

			else:
				rlist += [head]

	return rlist


def dep_opconvert(deplist):
	"""Move || and && to the beginning of the following arrays"""
	# Hack in management of the weird || for dep_wordreduce, etc.
	# dep_opconvert: [stuff, ["||", list, of, things]]
	# At this point: [stuff, "||", [list, of, things]]
	retlist = []
	x = 0
	while x != len(deplist):
		if isinstance(deplist[x], list):
			retlist.append(dep_opconvert(deplist[x]))
		elif deplist[x] == "||" or deplist[x] == "&&":
			retlist.append([deplist[x]] + dep_opconvert(deplist[x+1]))
			x += 1
		else:
			retlist.append(deplist[x])
		x += 1
	return retlist






class DependencyGraph(object):
	"""Self-contained directed graph of abstract nodes.

	This is a enhanced version of the digraph class. It supports forward
	and backward dependencies as well as primitive circular dependency
	resolution. It is fully self contained and requires only that nodes
	added to the graph are immutable.

	There are no validity checks done on the values passed to any method,
	but is written so that invalid data will either cause an exception to
	be raised. For this reason, this should not be used as part of any
	external API."""


	def __init__(self):
		"""Create an empty graph."""
		# The entire graph is stored inside this one dictionary.
		# The keys represent each node within the graph. Each node
		# is paired with a list of nodes depending on it and a list
		# of nodes it depends on. The complete structure is:
		# { node : ( [node], [node] ) }
		self.graph = {}

		# Strictly speaking, the graph shouldn't care about the order
		# that packages are added to the graph, but using it ensures
		# that system packages stay before world packages when pulling
		# nodes one at a time.
		self.order = []

	def clone(self):
		"""Create an exact duplicate of this graph."""
		clone = DependencyGraph()
		# A manual copy should save a slight amount of time, but
		# is dependent on whether python's deepcopy is implemented
		# in python or not. It is at the moment.
		for node in self.graph:
			clone.graph[node] = (self.graph[node][0][:],
			                     self.graph[node][1][:])
		clone.order = self.order[:]
		return clone

	def has_node(self, node):
		"""Indicate the existance of a node in the graph."""
		return self.graph.has_key(node)

	def add_node(self, node):
		"""Add a node to the graph if it hasn't been already."""
		if self.graph.has_key(node):
			return
		self.graph[node] = ([], [])
		self.order.append(node)

	def add_relationship(self, parent, child):
		"""Add a relationship between two pre-existing nodes."""
		# This code needs to raise an exception if either the
		# parent or child have not in fact been added prior.
		if parent not in self.graph[child][0]:
			self.graph[child][0].append(parent)
			self.graph[parent][1].append(child)

	def remove_relationship(self, parent, child):
		"""Remove an existing relationship between two nodes."""
		self.graph[child][0].remove(parent)
		self.graph[parent][1].remove(child)

	def get_relationships(self, node):
		"""Retrieve parent and children lists of a node.

		@rtype: ( [node], [node] )
		"""
		# This code also needs to raise an exception if the node
		# has not been added prior.
		relationships = (self.graph[node][0][:],
		                 self.graph[node][1][:])
		return relationships

	def remove_node(self, node):
		"""Remove a node from the graph, destroying any relationships.

		Any relationships destroyed by removing this node are returned.

		@rtype: ( [node], [node] )
		"""
		# This code also needs to raise an exception if the node
		# has not been added prior.

		relationships = self.get_relationships(node)

		# Ensuring that all relationships are destroyed keeps the
		# graph in a sane state. A node must _never_ depend on another
		# node that does not exist in the graph.
		for parent in relationships[0]:
			self.graph[parent][1].remove(node)
		for child in relationships[1]:
			self.graph[child][0].remove(node)

		# Kill of the other side of the relationships in one shot.
		del self.graph[node]

		# Make sure to remove the node from the ordered list as well.
		self.order.remove(node)

		return relationships

	def get_all_nodes(self):
		"""Return a list of every node in the graph.

		@rtype: [node]
		"""
		# Assuming our graph is in a sane state, self.order contains
		# the same set of nodes as self.graph.keys().
		return self.order[:]

	def get_leaf_nodes(self):
		"""Return a list of all nodes that have no child dependencies.

		If all nodes have child dependencies and the graph is not
		empty, circular dependency resolution is attempted. In such a
		circumstance, only one node is ever returned and is passed back
		by way of an exception.

		@rtype: [node]
		"""
		# If the graph is empty, just return an empty list.
		if not self.graph:
			return []

		# Iterate through the graph's nodes and add any that have no
		# child dependencies. If we find such nodes, return them.
		nodes = []
		for node in self.order:
			if not self.graph[node][1]:
				nodes.append(node)
		if nodes:
			return nodes

		# If we've got this far, then a circular dependency set that
		# contains every node. However, there is usually a subset of
		# nodes that are self-contained. We will find the subset with
		# the most parents so that circular dependencies can be dealt
		# with (and not have to be recalculated) as early as possible.

		# Create a list of tuples containing the number of parents
		# paired with the corresponding node.
		counts = []
		# We'll keep a record of the actual parents for later on.
		parents = {}
		for node in self.graph:
			parents[node] = self.get_parent_nodes(node, depth=0)
			if len(parents[node]) == len(self.graph):
				# XXX: Every node in the graph depends on
				# this node. Following the logic through will
				# return this node or another that has equal
				# number of parents, so shortcut it here.
				return [node]
			counts += [(len(parents[node]), node)]

		# Reverse sort the generated list.
		counts.sort()
		counts.reverse()

		# Find the first node that is in a circular dependency set.
		for count in counts:
			node = count[1]
			children = self.get_child_nodes(node, depth=0)
			if node in children:
				break

		# Now we'll order the nodes in the set by parent count.
		counts = []
		for node in children:
			counts += [(len(parents[node]), node)]

		# Reverse sort the generated list.
		counts.sort()
		counts.reverse()

		# Return the first node in the list.
		# XXX: This needs to be changed into an exception.
		return [counts[0][1]]

	def get_root_nodes(self):
		"""Return the smallest possible list of starting nodes.

		Ordinarily, all nodes with no parent nodes are returned.
		However, if there are any circular dependencies that can
		not be reached through one of these nodes, they will be
		resolved and a suitable starting node chosen.

		@rtype: [node]
		"""
		# Create a copy of our graph.
		clone = self.clone()

		# Keep processing the graph until it is empty.
		roots = []
		while clone.graph:

			# Find all nodes that have no parent nodes.
			newroots = []
			for node in clone.order:
				if not clone.graph[node][0]:
					newroots.append(node)

			# Remove them and all their descendents from the graph.
			for node in newroots:
				for child in clone.get_child_nodes(node, depth=0):
					clone.remove_node(child)
				clone.remove_node(node)

			# And add them to our list of root nodes.
			roots.extend(newroots)

			# If the graph is empty, stop processing.
			if not clone.graph:
				break

			# If the graph isn't empty, then we have a circular
			# dependency. We'll just remove one leaf node and
			# then look for parentless nodes again.
			clone.remove_node(clone.get_leaf_nodes()[0])

		# Sort the list of roots by the node addition order.
		newroots = self.order[:]
		for x in range(len(newroots)-1,-1,-1):
			if newroots[x] not in roots:
				del newroots[x]

		# Return the sorted list.
		return newroots

	def get_parent_nodes(self, node, depth=1):
		"""Return a list of nodes that depend on a node.

		The examined node will be included in the returned list
		if the node exists in a circular dependency.

		@param depth: Maximum depth to recurse to, or 0 for all.
		@rtype: [node]
		"""
		return self.__traverse_nodes(node, depth, 0)

	def get_child_nodes(self, node, depth=1):
		"""Return a list of nodes depended on by node.

		The examined node will be included in the returned list
		if the node exists in a circular dependency.

		@param depth: Maximum depth to recurse to, or 0 for all.
		@rtype: [node]
		"""
		return self.__traverse_nodes(node, depth, 1)

	def __traverse_nodes(self, origin, depth, path):
		# Set depth to the maximum if it is 0.
		if not depth:
			depth = len(self.graph)

		traversed = {}  # The list of nodes to be returned

		# This function _needs_ to be fast, so we use a stack
		# based implementation rather than recursive calls.
		stack = []      # Stack of previous depths
		node = origin   # The current node we are checking
		index = 0       # Progress through the node's relations
		length = len(self.graph[node][path])

		graph = self.graph   # Faster access via local scope

		# Repeat while the stack is not empty or there are more
		# relations to be processed for the current node.
		while stack or length != index:

			# If we're finished at the current depth, move back up.
			if index == length:
				(depth, node, index, length) = stack.pop()

			# Otherwise, process the next relation.
			else:
				relation = graph[node][path][index]
				# Add the relation to our list if necessary...
				if relation not in traversed:
					traversed[relation] = None
					# ...and then check if we can go deeper
					if depth != 1:
						# Add state to the stack.
						stack += [(depth, node, index, length)]
						# Reset state for the new node.
						depth -= 1
						node = relation
						index = 0
						length = len(graph[node][path])
						# Restart the loop.
						continue

			# Move onto the next relation.
			index += 1

		# Return our list.
		return traversed.keys()

def dep_getkey(mydep):
	if not len(mydep):
		return mydep
	if mydep[0]=="*":
		mydep=mydep[1:]
	if mydep[-1]=="*":
		mydep=mydep[:-1]
	if mydep[0]=="!":
		mydep=mydep[1:]
	if mydep[:2] in [ ">=", "<=" ]:
		mydep=mydep[2:]
	elif mydep[:1] in "=<>~":
		mydep=mydep[1:]
	if isspecific(mydep):
		mysplit=portage_versions.catpkgsplit(mydep)
		if not mysplit:
			return mydep
		return mysplit[0]+"/"+mysplit[1]
	else:
		return mydep


iscache={}
def isspecific(mypkg):
	"now supports packages with no category"
	if mypkg in iscache:
		return iscache[mypkg]
	mysplit=mypkg.split("/")
	if not isjustname(mysplit[-1]):
		iscache[mypkg]=1
		return 1
	iscache[mypkg]=0
	return 0

def match_to_list(mypkg,mylist):
	"""(pkgname,list)
	Searches list for entries that matches the package.
	"""
	matches=[]
	for x in mylist:
		if match_from_list(x,[mypkg]):
			if x not in matches:
				matches.append(x)
	return matches

def best_match_to_list(mypkg,mylist):
	"""(pkgname,list)
	Returns the most specific entry (assumed to be the longest one)
	that matches the package given.
	"""
	# XXX Assumption is wrong sometimes.
	maxlen = 0
	bestm  = None
	for x in match_to_list(mypkg,mylist):
		if len(x) > maxlen:
			maxlen = len(x)
			bestm  = x
	return bestm



def match_from_list(mydep,candidate_list):
	if mydep[0] == "!":
		mydep = mydep[1:]

	mycpv     = dep_getcpv(mydep)
	mycpv_cps = portage_versions.catpkgsplit(mycpv) # Can be None if not specific

	if not mycpv_cps:
		cat,pkg = portage_versions.catsplit(mycpv)
		ver     = None
		rev     = None
	else:
		cat,pkg,ver,rev = mycpv_cps
		if mydep == mycpv:
			raise KeyError, "Specific key requires an operator (%s) (try adding an '=')" % (mydep)

	if ver and rev:
		operator = get_operator(mydep)
		if not operator:
			writemsg("!!! Invanlid atom: %s\n" % mydep)
			return []
	else:
		operator = None

	mylist = []

	if operator == None:
		for x in candidate_list:
			xs = portage_versions.pkgsplit(x)
			if xs == None:
				if x != mycpv:
					continue
			elif xs[0] != mycpv:
				continue
			mylist.append(x)

	elif operator == "=": # Exact match
		if mycpv in candidate_list:
			mylist = [mycpv]

	elif operator == "=*": # glob match
		# The old verion ignored _tag suffixes... This one doesn't.
		for x in candidate_list:
			if x[0:len(mycpv)] == mycpv:
				mylist.append(x)

	elif operator == "~": # version, any revision, match
		for x in candidate_list:
			xs = portage_versions.catpkgsplit(x)
			if xs[0:2] != mycpv_cps[0:2]:
				continue
			if xs[2] != ver:
				continue
			mylist.append(x)

	elif operator in [">", ">=", "<", "<="]:
		for x in candidate_list:
			try:
				result = portage_versions.pkgcmp(portage_versions.pkgsplit(x), [cat+"/"+pkg,ver,rev])
			except SystemExit, e:
				raise
			except:
				writemsg("\nInvalid package name: %s\n" % x)
				sys.exit(73)
			if result == None:
				continue
			elif operator == ">":
				if result > 0:
					mylist.append(x)
			elif operator == ">=":
				if result >= 0:
					mylist.append(x)
			elif operator == "<":
				if result < 0:
					mylist.append(x)
			elif operator == "<=":
				if result <= 0:
					mylist.append(x)
			else:
				raise KeyError, "Unknown operator: %s" % mydep
	else:
		raise KeyError, "Unknown operator: %s" % mydep

	return mylist


def prepare_prefdict(preferences):
	myprefdict = {}
	idx = 0
	for atom in preferences:
		if atom.cpv.key not in myprefdict:
			myprefdict[atom.cpv.key] = []
		myprefdict[atom.cpv.key].append((idx, atom))
		idx += 1
	myprefdict["____"] = idx
	return myprefdict


def transform_dependspec(dependspec, prefdict):
	def dotransform(dependspec, prefdict):
		dependspec = copy.copy(dependspec)
		elements = dependspec.elements
		dependspec.elements = []
		neworder = []
		prio = prefdict["____"]
		for element in elements[:]:
			if isinstance(element, portage_syntax.DependSpec):
				neworder.append(dotransform(element, prefdict))
				elements.remove(element)
			elif element.cpv.key in prefdict:
				for (idx, pref) in prefdict[element.cpv.key]:
					if pref.intersects(element):
						if idx < prio:
							prio = idx
						if pref.encapsulates(element):
							neworder.append((idx, element))
							elements.remove(element)
						else:
							subdependspec = portage_syntax.DependSpec(element_class=portage_syntax.Atom)
							if element.encapsulates(pref):
								subsubdependspec = portage_syntax.DependSpec(element_class=portage_syntax.Atom)
								subsubdependspec.add_element(pref)
								subsubdependspec.add_element(element)
								subdependspec.add_element(subsubdependspec)
							else:
								subdependspec.add_element(pref)
							subdependspec.add_element(element)
							subdependspec.preferential = True
							neworder.append((idx, subdependspec))
							elements.remove(element)
		neworder.sort()
		for element in neworder:
			dependspec.add_element(element[1])
		for element in elements:
			dependspec.add_element(element)
		return (prio, dependspec)
	return dotransform(dependspec, prefdict)[1]


def transform_virtuals(pkg, dependspec, virtuals):
	dependspec = copy.copy(dependspec)
	elements = dependspec.elements
	dependspec.elements = []
	for element in elements:
		if isinstance(element, portage_syntax.DependSpec):
			dependspec.elements.append(transform_virtuals(pkg, element, virtuals))
		elif element.cpv.key not in virtuals:
			dependspec.elements.append(element)
		else:
			subdepspec = portage_syntax.DependSpec(element_class=portage_syntax.Atom)
			subdepspec.preferential = True
			for virtual in virtuals[element.cpv.key]:
				atom = element.with_key(virtual)
				if not atom.match(pkg):
					subdepspec.add_element(element.with_key(virtual))
			dependspec.elements.append(subdepspec)
	return dependspec


class StateGraph(object):

	def __init__(self):
		# key : (bool, [GluePkg], [GluePkg], [Atom], [Atom])
		self.pkgrec = {}
		# key : [Atom]
		self.unmatched_atoms = {}
		# [Atom]
		self.unmatched_preferentials = []
		# key : [pkg, [[Atom]]]
		self.preferential_atoms = {}
		# key : [key]
		self.reverse_preferentials = {}

	def get_unmatched_atoms(self):
		unmatched = []
		for key in self.unmatched_atoms:
			unmatched.append(self.unmatched_atoms[key][0])
		return unmatched

	def get_unmatched_preferentials(self):
		return self.unmatched_preferentials[:]

	def get_unneeded_packages(self):
		unneeded = []
		for key in self.pkgrec:
			unneeded.extend(self.pkgrec[key][1])
		return unneeded

	def get_needed_packages(self):
		needed = []
		for key in self.pkgrec:
			needed.extend(self.pkgrec[key][0])
		return needed

	def get_conflicts(self):
		conflicts = []
		for key in self.pkgrec:
			slots = {}
			in_conflict = False
			for pkg in self.pkgrec[key][0]:
				if pkg.slot in slots:
					slots[pkg.slot].append(pkg)
					in_conflict = True
				else:
					slots[pkg.slot] = [pkg]
			if in_conflict:
				for slot in slots:
					if len(slots[slot]) > 1:
						conflicts.append(slots[slot])
		return conflicts

	def add_package(self, pkg, keep=False):
		key = pkg.key
		if key not in self.pkgrec:
			self.pkgrec[key] = ([], [pkg], [], [], [keep])
		else:
			if not self.pkgrec[key][4][0]:
				self.pkgrec[key][4][0] = keep
			self.pkgrec[key][1].append(pkg)
		self._recheck(key)

	def remove_package(self, pkg):
		key = pkg.key
		if pkg not in self.pkgrec[key][1]:
			self._demote_pkg(pkg)
		self.pkgrec[key][1].remove(pkg)
		self._recheck(key)

	def _recheck(self, key):
		(used, unused, unmatched) = self._select_pkgs(key)
		for pkg in used:
			if pkg not in self.pkgrec[key][0]:
				self._promote_pkg(pkg)
		for pkg in unused:
			if pkg not in self.pkgrec[key][1]:
				self._demote_pkg(pkg)
		if key in self.unmatched_atoms:
			del self.unmatched_atoms[key]
		for idx in range(len(self.unmatched_preferentials)-1, -1, -1):
			if self.unmatched_preferentials[idx].cpv.key == key:
				del self.unmatched_preferentials[idx]
		if unmatched:
			for atom in unmatched:
				if atom in self.pkgrec[key][2]:
					if key in self.unmatched_atoms:
						self.unmatched_atoms[key].append(atom)
					else:
						self.unmatched_atoms[key] = [atom]
				else:
					self.unmatched_preferentials.append(atom)
		if not self.pkgrec[key][0] and not self.pkgrec[key][1] and not self.pkgrec[key][2] and not self.pkgrec[key][3] and not self.pkgrec[key][4][0]:
			del self.pkgrec[key]

	def _select_pkgs(self, key):
		allpkgs = self.pkgrec[key][0] + self.pkgrec[key][1]
		used = []
		unused = []
		regular_atoms = []
		unmatched = []
		for atom in self.pkgrec[key][2] + self.pkgrec[key][3]:
			if atom.blocks:
				for pkg in allpkgs[:]:
					if atom.match(pkg):
						allpkgs.remove(pkg)
						unused.append(pkg)
			elif atom not in regular_atoms:
				regular_atoms.append(atom)

		if regular_atoms:
			slots = {}
			for pkg in allpkgs:
				if pkg.slot not in slots:
					slots[pkg.slot] = []
				slots[pkg.slot].append(pkg)

			used_slots = []
			multislot_atoms = []
			for atom in regular_atoms:
				matched_slots = []
				for slot in slots:
					for pkg in slots[slot]:
						if atom.match(pkg):
							matched_slots.append(slot)
							break
					if len(matched_slots) > 1:
						multislot_atoms.append(atom)
						break
				if atom in multislot_atoms:
					continue
				if not matched_slots:
					unmatched.append(atom)
					continue
				slot = matched_slots[0]
				if slot not in used_slots:
					used_slots.append(slot)
				for idx in range(len(slots[slot])-1, -1, -1):
					if not atom.match(slots[slot][idx]):
						unused.append(slots[slot][idx])
						del slots[slot][idx]
			used = []
			uncertain = []
			for slot in slots:
				if slot in used_slots:
					used.extend(slots[slot])
				else:
					uncertain.extend(slots[slot])
			for atom in multislot_atoms:
				matched = False
				for pkg in used[:]:
					if atom.match(pkg):
						matched = True
						break
				if matched:
					continue
				for pkg in uncertain:
					if atom.match(pkg):
						uncertain.remove(pkg)
						used.append(pkg)
						matched = True
						break
				if not matched:
					unmatched.append(atom)
			unused.extend(uncertain)
		elif self.pkgrec[key][4][0]:
			used = allpkgs
		else:
			unused = allpkgs
		return (used, unused, unmatched)

	def _promote_pkg(self, pkg):
		key = pkg.key
		checks = {}
		self.pkgrec[key][1].remove(pkg)
		self.pkgrec[key][0].append(pkg)
		if not pkg.rdeps.preferential:
			for atom in pkg.rdeps.elements:
				if atom.cpv.key not in self.pkgrec:
					self.pkgrec[atom.cpv.key] = ([], [], [atom], [], [False])
				else:
					self.pkgrec[atom.cpv.key][2].append(atom)
				if atom.cpv.key not in checks:
					checks[atom.cpv.key] = True
		else:
			preflist = [pkg, []]
			if isinstance(pkg.rdeps.elements[0], portage_syntax.Atom):
				for atom in pkg.rdeps.elements:
					preflist[1].append([atom])
			else:
				for option in pkg.rdeps.elements:
					preflist[1].append([])
					for atom in option.elements:
						preflist[1][-1].append(atom)
			for option in preflist[1]:
				for atom in option:
					if atom.cpv.key not in self.pkgrec:
						self.pkgrec[atom.cpv.key] = ([], [], [], [atom], [False])
					else:
						self.pkgrec[atom.cpv.key][3].append(atom)
					if atom.cpv.key not in self.reverse_preferentials:
						self.reverse_preferentials[atom.cpv.key] = {}
					if key not in self.reverse_preferentials[atom.cpv.key]:
						self.reverse_preferentials[atom.cpv.key][key] = 1
					else:
						self.reverse_preferentials[atom.cpv.key][key] += 1
					checks[atom.cpv.key] = True
			if key not in self.preferential_atoms:
				self.preferential_atoms[key] = [preflist]
			else:
				self.preferential_atoms[key].append(preflist)
			self._check_preferentials(key)
		if key in self.reverse_preferentials:
			for parent in self.reverse_preferentials[key].keys():
				self._check_preferentials(parent)
		for key in checks:
			if key in self.pkgrec:
				self._recheck(key)

	def _demote_pkg(self, pkg):
		key = pkg.key
		checks = {}
		self.pkgrec[key][0].remove(pkg)
		self.pkgrec[key][1].append(pkg)
		if not pkg.rdeps.preferential:
			for atom in pkg.rdeps.elements:
				self.pkgrec[atom.cpv.key][2].remove(atom)
				if not self.pkgrec[atom.cpv.key][0] and not self.pkgrec[atom.cpv.key][1] and not self.pkgrec[atom.cpv.key][2] and not self.pkgrec[atom.cpv.key][3]:
					del self.pkgrec[atom.cpv.key]
					if atom.cpv.key in self.unmatched_atoms:
						del self.unmatched_atoms[atom.cpv.key]
				else:
					checks[atom.cpv.key] = True
		else:
			for idx in range(len(self.preferential_atoms[key])):
				if self.preferential_atoms[key][idx][0] == pkg:
					for atomlist in self.preferential_atoms[key][idx][1]:
						for atom in atomlist:
							self.pkgrec[atom.cpv.key][3].remove(atom)
							self.reverse_preferentials[atom.cpv.key][key] -= 1
							if not self.reverse_preferentials[atom.cpv.key][key]:
								del self.reverse_preferentials[atom.cpv.key][key]
								if not self.reverse_preferentials[atom.cpv.key]:
									del self.reverse_preferentials[atom.cpv.key]
							checks[atom.cpv.key] = True
					del self.preferential_atoms[key][idx]
					if not self.preferential_atoms[key]:
						del self.preferential_atoms[key]
		if key in self.reverse_preferentials:
			for parent in self.reverse_preferentials[key].keys():
				self._check_preferentials(parent)
		for key in checks:
			if key in self.pkgrec:
				self._recheck(key)

	def _check_preferentials(self, key):
		checks = {}
		for preflist in self.preferential_atoms[key]:
			if len(preflist[1]) == 1:
				all_matched = True
				for atom in preflist[1][0]:
					matched = False
					for pkg in self.pkgrec[atom.cpv.key][0]:
						if atom.match(pkg):
							matched = True
							break
					if not matched:
						all_matched = False
						break
				if not all_matched:
					pkg = preflist[0]
					self._demote_pkg(pkg)
					self._promote_pkg(pkg)
					self._check_preferentials(key)
					return
			else:
				for idx in range(len(preflist[1])):
					all_matched = True
					for atom in preflist[1][idx]:
						matched = False
						for pkg in self.pkgrec[atom.cpv.key][0]:
							if atom.match(pkg):
								matched = True
								break
						if not matched:
							all_matched = False
							break
					if all_matched:
						removable = preflist[1][:idx] + preflist[1][idx+1:]
						preflist[1] = [preflist[1][idx]]
						for option in removable:
							for atom in option:
								self.pkgrec[atom.cpv.key][3].remove(atom)
								self.reverse_preferentials[atom.cpv.key][key] -= 1
								if not self.reverse_preferentials[atom.cpv.key][key]:
									del self.reverse_preferentials[atom.cpv.key][key]
									if not self.reverse_preferentials[atom.cpv.key]:
										del self.reverse_preferentials[atom.cpv.key]
								checks[atom.cpv.key] = True
						break
		for key in checks:
			self._recheck(key)
