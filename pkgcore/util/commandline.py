# Copyright: 2005-2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.util.containers import InvertedContains
from pkgcore.restrictions import packages, values, boolean, util
from pkgcore.package import cpv, atom


def convert_glob(token):
	if len(filter(None, token.split("*"))) > 1:
		raise TypeError("'*' must be specified at the end or beginning of a matching field")
	if token.startswith("*"):
		if token.endswith("*"):
			return values.ContainmentMatch(token.strip("*"))
		return values.StrGlobMatch(token.strip("*"), prefix=False)
	elif token.endswith("*"):
		return values.StrGlobMatch(token.strip("*"), prefix=True)
	elif not token:
		return None
	return values.StrExactMatch(token)

def collect_ops(text):
	i = 0
	while text[i] in ("<", "=", ">", "~"):
		i+=1
	return text[0:i], text[i:]

def generate_restriction(text):
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
	if "*" not in text and len(tsplit) != 1:
		a = atom.atom(text)
		# force expansion
		a.key
		return a
	if len(tsplit) == 1:
		r = convert_glob(tsplit[0])
		if not r:
			return packages.AlwaysTrue
		return packages.PackageRestriction("package", r)
	
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
