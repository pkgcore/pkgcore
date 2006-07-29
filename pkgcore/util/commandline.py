# Copyright: 2005-2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
common commandline processing, including simplified atom generation
"""

from pkgcore.util.containers import InvertedContains
from pkgcore.restrictions import packages, values, boolean, util
from pkgcore.package import cpv, atom


def convert_glob(token):
	if len(filter(None, token.split("*"))) > 1:
		raise TypeError("'*' must be specified at the end or beginning of a matching field")
	l = len(token)
	if token.startswith("*") and l > 1:
		if token.endswith("*"):
			if l == 2:
				return None
			return values.ContainmentMatch(token.strip("*"))
		return values.StrGlobMatch(token.strip("*"), prefix=False)
	elif token.endswith("*") and l > 1:
		return values.StrGlobMatch(token.strip("*"), prefix=True)
	elif l <= 1:
		return None
	return values.StrExactMatch(token)

def collect_ops(text):
	i = 0
	while text[i] in ("<", "=", ">", "~"):
		i+=1
	return text[0:i], text[i:]

def generate_restriction(text):

	"""generate appropriate restriction for text

	Parsing basically breaks it down into chunks split by /, with each chunk allowing for 
	prefix/postfix globbing- note that a postfixed glob on package token is treated as package attribute
	matching, B{not} as necessarily a version match.
	
	If only one chunk is found, it's treated as a package chunk.  Finally, it supports a nonstandard variation of atom syntax
	where the category can be dropped.
	
	Examples-
	  - "*": match all
	  - "dev-*/*": category must start with dev-
	  - "dev-*": package must start with dev-
	  - *-apps/portage*: category must end in -apps, package must start with portage
	  - >=portage-2.1: atom syntax, package portage, version greater then or equal to 2.1

	@param text: string to attempt to parse
	@type text: string
	@return: L{package restriction<pkgcore.restrictions.packages>} derivative
	"""
	
	orig_text = text = text.strip()
	if "!" in text:
		raise ValueError("!, or any form of blockers make no sense in this usage: %s" % text)
	tsplit = text.rsplit("/", 1)
	if len(tsplit) == 1:
		ops, text = collect_ops(text)
		if not ops:
			r = convert_glob(text)
			if r is None:
				return packages.AlwaysTrue
			return packages.PackageRestriction("package", r)
		elif text.startswith("*"):
			raise ValueError("cannot do prefix glob matches with version ops: %s" % orig_text)
		# ok... fake category.  whee.
		r = list(util.collect_package_restrictions(atom.atom("%scategory/%s" % (ops, text)).restrictions,
			attrs=InvertedContains(["category"])))
		if len(r) == 1:
			return r[0]
		return packages.AndRestriction(*r)
	if "*" not in text:
		a = atom.atom(text)
		# force expansion
		a.key
		return a

	r = map(convert_glob, tsplit)
	if not r[0] and not r[1]:
		return packages.AlwaysTrue
	if not r[0]:
		return packages.PackageRestriction("package", r[1])
	elif not r[1]:
		return packages.PackageRestriction("category", r[0])
	return packages.AndRestriction(
		packages.PackageRestriction("category", r[0]),
		packages.PackageRestriction("package", r[1]))
