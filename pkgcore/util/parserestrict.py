# Copyright: 2005-2006 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

"""Functions that turn a string into a restriction or raise ParseError.

@var parse_funcs: dict of the functions that are available.
"""

from pkgcore.util.containers import InvertedContains
from pkgcore.restrictions import packages, values, util
from pkgcore.package import errors
from pkgcore.ebuild import atom, cpv, cpv_errors


class ParseError(ValueError):
    """Raised if parsing a restriction expression failed."""


def comma_separated_containment(attr):
    """Helper for parsing comma-separated strings to a ContainmentMatch.

    @param attr: name of the attribute.
    @returns: a parse function: takes a string of comma-separated values,
        returns a L{packages.PackageRestriction} matching packages that
        have any of those values in the attribute passed to this function.
    """
    def _parse(value):
        return packages.PackageRestriction(attr, values.ContainmentMatch(*(
                    piece.strip() for piece in value.split(','))))
    return _parse


def convert_glob(token):
    if '*' in token[1:-1]:
        raise ParseError(
            "'*' must be specified at the end or beginning of a matching field")
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

def parse_match(text):

    """generate appropriate restriction for text

    Parsing basically breaks it down into chunks split by /, with each
    chunk allowing for prefix/postfix globbing- note that a postfixed
    glob on package token is treated as package attribute matching,
    B{not} as necessarily a version match.

    If only one chunk is found, it's treated as a package chunk.
    Finally, it supports a nonstandard variation of atom syntax where
    the category can be dropped.

    Examples-
      - "*": match all
      - "dev-*/*": category must start with dev-
      - "dev-*": package must start with dev-
      - *-apps/portage*: category must end in -apps,
          package must start with portage
      - >=portage-2.1: atom syntax, package portage,
          version greater then or equal to 2.1

    @param text: string to attempt to parse
    @type text: string
    @return: L{package restriction<pkgcore.restrictions.packages>} derivative
    """

    orig_text = text = text.strip()
    if "!" in text:
        raise ParseError(
            "!, or any form of blockers make no sense in this usage: %s" % (
                text,))
    tsplit = text.rsplit("/", 1)
    if len(tsplit) == 1:
        ops, text = collect_ops(text)
        if not ops:
            if "*" in text:
                r = convert_glob(text)
                if r is None:
                    return packages.AlwaysTrue
                return packages.PackageRestriction("package", r)
        elif text.startswith("*"):
            raise ParseError(
                "cannot do prefix glob matches with version ops: %s" % (
                    orig_text,))
        # ok... fake category.  whee.
        try:
            r = list(util.collect_package_restrictions(
                    atom.atom("%scategory/%s" % (ops, text)).restrictions,
                    attrs=InvertedContains(["category"])))
        except atom.MalformedAtom, e:
            raise ParseError(str(e))
        if len(r) == 1:
            return r[0]
        return packages.AndRestriction(*r)
    elif text[0] in "=<>~":
        return atom.atom(text)
    if "*" not in text:
        try:
            return atom.atom(text)
        except errors.InvalidPackage, e:
            raise ParseError(str(e))
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


def parse_pv(repo, text):
    """Return a CPV instance from either a cpv or a pv string.

    If a pv is passed it needs to match a single cpv in repo.
    """
    try:
        return cpv.CPV(text)
    except cpv_errors.InvalidCPV:
        restrict = parse_match('=%s' % (text,))
        result = None
        for match in repo.itermatch(restrict):
            if result is not None:
                raise ParseError('multiple matches for %s (%s, %s)' % (
                        text, result.cpvstr, match.cpvstr))
            result = match
        if result is None:
            raise ParseError('no matches for %s' % (text,))
        return cpv.CPV(result.category, result.package, result.version)


parse_funcs = {
    'match': parse_match,
    }
