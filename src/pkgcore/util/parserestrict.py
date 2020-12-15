"""Functions that turn a string into a restriction or raise ParseError.

__all__ = ("parse_match", "ParseError",)

@var parse_funcs: dict of the functions that are available.
"""

import re

from ..ebuild import atom, cpv, errors, restricts
from ..restrictions import packages, values
from ..restrictions.util import collect_package_restrictions

valid_globbing = re.compile(r"^(?:[\w+-.]+|(?<!\*)\*)+$").match


class ParseError(ValueError):
    """Raised if parsing a restriction expression failed."""


def comma_separated_containment(attr, values_kls=frozenset, token_kls=str):
    """Helper for parsing comma-separated strings to a ContainmentMatch2.

    :param attr: name of the attribute.
    :return: a parse function: takes a string of comma-separated values,
        returns a :obj:`packages.PackageRestriction` matching packages that
        have any of those values in the attribute passed to this function.
    """
    def _parse(value):
        return packages.PackageRestriction(
            attr, values.ContainmentMatch2(
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
        raise ParseError(
            "globs must be composed of [\\w-.+], with optional "
            f"'*'- {token!r} is disallowed however")
    pattern = re.escape(token).replace('\\*', '.*')
    pattern = f"^{pattern}$"
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
    - dev-qt/*:5: all Qt 5 libs
    - boost:0/1.60: all packages named boost with a slot/subslot of 0/1.60.0

    :param text: string to attempt to parse
    :type text: string
    :return: :obj:`pkgcore.restrictions.packages` derivative
    """

    orig_text = text = text.strip()
    if "!" in text:
        raise ParseError(
            f"'!' or any form of blockers make no sense in this usage: {text!r}")

    restrictions = []
    if '::' in text:
        text, repo_id = text.rsplit('::', 1)
        restrictions.append(restricts.RepositoryDep(repo_id))
    if ':' in text:
        text, slot = text.rsplit(':', 1)
        slot, _sep, subslot = slot.partition('/')
        if slot:
            if '*' in slot:
                r = convert_glob(slot)
                if r is not None:
                    restrictions.append(packages.PackageRestriction("slot", r))
            else:
                restrictions.append(restricts.SlotDep(slot))
        if subslot:
            if '*' in subslot:
                if r is not None:
                    restrictions.append(packages.PackageRestriction("subslot", r))
            else:
                restrictions.append(restricts.SubSlotDep(subslot))

    tsplit = text.rsplit("/", 1)
    if len(tsplit) == 1:
        ops, text = collect_ops(text)
        if not ops:
            if "*" in text:
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
                f"cannot do prefix glob matches with version ops: {orig_text}")
        # ok... fake category.  whee.
        try:
            r = list(collect_package_restrictions(
                     atom.atom(f"{ops}category/{text}").restrictions,
                     attrs=("category",), invert=True))
        except errors.MalformedAtom as e:
            e.atom = orig_text
            raise ParseError(str(e)) from e
        if not restrictions and len(r) == 1:
            return r[0]
        restrictions.extend(r)
        return packages.AndRestriction(*restrictions)
    elif text[0] in atom.valid_ops or '*' not in text:
        # possibly a valid atom object
        try:
            return atom.atom(orig_text)
        except errors.MalformedAtom as e:
            if '*' not in text:
                raise ParseError(str(e)) from e
            # support globbed targets with version restrictions
            return packages.AndRestriction(*parse_globbed_version(text, orig_text))

    r = list(map(convert_glob, tsplit))
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


def parse_globbed_version(text, orig_text):
    """Support parsing globbed targets with limited version restrictions.

    For example, '>=*/alsa-*-1.1.7' would match all packages named 'alsa-*'
    that are version 1.1.7 or greater.
    """
    restrictions = []
    # find longest matching op
    op = max(x for x in atom.valid_ops if text.startswith(x))
    text = text[len(op):]
    # determine pkg version
    chunks = text.rsplit('-', 1)
    if len(chunks) == 1:
        raise ParseError(f'missing valid package version: {orig_text!r}')
    version_txt = chunks[-1]
    version = cpv.isvalid_version_re.match(version_txt)
    if not version:
        if '*' in version_txt:
            raise ParseError(
                f'operator {op!r} invalid with globbed version: {version_txt!r}')
        raise ParseError(f'missing valid package version: {orig_text!r}')
    restrictions.append(restricts.VersionMatch(op, version.group(0)))
    # parse the remaining chunk
    restrictions.append(parse_match(chunks[0]))
    return restrictions


def parse_pv(repo, text):
    """Return a CPV instance from either a cpv or a pv string.

    If a pv is passed it needs to match a single cpv in repo.
    """
    try:
        return cpv.CPV.versioned(text)
    except errors.InvalidCPV:
        restrict = parse_match(f"={text}")
        result = None
        for match in repo.itermatch(restrict):
            if result is not None:
                raise ParseError(
                    f"multiple matches for {text} ({result.cpvstr}, {match.cpvstr})")
            result = match
        if result is None:
            raise ParseError(f"no matches for {text}")
        return cpv.CPV(result.category, result.package, result.version)


parse_funcs = {
    'match': parse_match,
}
