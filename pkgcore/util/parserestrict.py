# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

"""Functions that turn a string into a restriction or raise ParseError.

__all__ = ("parse_match", "ParseError",)

@var parse_funcs: dict of the functions that are available.
"""

import re

from snakeoil.compatibility import raise_from, is_py3k

from pkgcore.restrictions import packages, values, util
from pkgcore.ebuild import atom, cpv, errors, restricts

valid_globbing = re.compile(r"^(?:[\w+-.]+|(?<!\*)\*)+$").match

class ParseError(ValueError):
    """Raised if parsing a restriction expression failed."""


def comma_separated_containment(attr, values_kls=frozenset, token_kls=str):
    """Helper for parsing comma-separated strings to a ContainmentMatch.

    :param attr: name of the attribute.
    :returns: a parse function: takes a string of comma-separated values,
        returns a :obj:`packages.PackageRestriction` matching packages that
        have any of those values in the attribute passed to this function.
    """
    def _parse(value):
        return packages.PackageRestriction(attr,
            values.ContainmentMatch2(
                values_kls(token_kls(piece.strip()) for piece in value.split(','))
            )
        )
    return _parse


def convert_glob(token):
    if token in ('*', ''):
        return None
    elif '*' not in token:
        return values.StrExactMatch(token)
    elif not valid_globbing(token):
        raise ParseError("globs must be composed of [\w-.+], with optional "
            "'*'- '%s' is disallowed however" % token)
    pattern = "^%s$" % (re.escape(token).replace("\*", ".*"),)
    return values.StrRegex(pattern, match=True)

def collect_ops(text):
    i = 0
    while i < len(text) and text[i] in ("<", "=", ">", "~"):
        i += 1
    return text[0:i], text[i:]

def parse_match(text):
    """generate appropriate restriction for text

    Parsing basically breaks it down into chunks split by /, with each
    chunk allowing for prefix/postfix globbing- note that a postfixed
    glob on package token is treated as package attribute matching,
    not as necessarily a version match.

    If only one chunk is found, it's treated as a package chunk.
    Finally, it supports a nonstandard variation of atom syntax where
    the category can be dropped.

    Examples:

    - `*`: match all
    - `dev-*/*`: category must start with 'dev-'
    - `dev-*`: package must start with 'dev-'
    - `*-apps/portage*`: category must end in '-apps', package must start with
      'portage'
    - `>=portage-2.1`: atom syntax, package 'portage', version greater then or
      equal to '2.1'

    :param text: string to attempt to parse
    :type text: string
    :return: :obj:`pkgcore.restrictions.packages` derivative
    """

    # Ensure the text var is a string if we're under py3k.
    if not is_py3k:
        text = text.encode('ascii')
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
                restrictions = []
                if '::' in text:
                    text, repo_id = text.rsplit('::', 1)
                    restrictions.append(restricts.RepositoryDep(repo_id))
                r = convert_glob(text)
                if r is None:
                    restrictions.append(packages.AlwaysTrue)
                else:
                    restrictions.append(packages.PackageRestriction("package", r))
                if len(restrictions) == 1:
                    return restrictions[0]
                return packages.AndRestriction(*restrictions)
        elif text.startswith("*"):
            raise ParseError(
                "cannot do prefix glob matches with version ops: %s" % (
                    orig_text,))
        # ok... fake category.  whee.
        try:
            r = list(util.collect_package_restrictions(
                    atom.atom("%scategory/%s" % (ops, text)).restrictions,
                    attrs=("category",), invert=True))
        except errors.MalformedAtom as e:
            raise_from(ParseError(str(e)))
        if len(r) == 1:
            return r[0]
        return packages.AndRestriction(*r)
    elif text[0] in "=<>~":
        try:
            return atom.atom(text)
        except errors.MalformedAtom as e:
            raise_from(ParseError(str(e)))
    if "*" not in text:
        try:
            return atom.atom(text)
        except errors.MalformedAtom as e:
            raise_from(ParseError(str(e)))

    restrictions = []
    if '::' in tsplit[1]:
        tsplit[1], repo_id = tsplit[1].rsplit('::', 1)
        restrictions.append(restricts.RepositoryDep(repo_id))
    r = map(convert_glob, tsplit)
    if not r[0] and not r[1]:
        restrictions.append(packages.AlwaysTrue)
    elif not r[0]:
        restrictions.append(packages.PackageRestriction("package", r[1]))
    elif not r[1]:
        restrictions.append(packages.PackageRestriction("category", r[0]))
    else:
        restrictions.extend((
            packages.PackageRestriction("category", r[0]),
            packages.PackageRestriction("package", r[1]),
        ))
    if len(restrictions) == 1:
        return restrictions[0]
    return packages.AndRestriction(*restrictions)


def parse_pv(repo, text):
    """Return a CPV instance from either a cpv or a pv string.

    If a pv is passed it needs to match a single cpv in repo.
    """
    try:
        return cpv.CPV.versioned(text)
    except errors.InvalidCPV:
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
