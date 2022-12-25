"""atom parsing utility"""

import re
from functools import partial

from ..ebuild.atom import atom as atom_cls
from ..ebuild.errors import MalformedAtom
from ..util.commandline import ArgumentParser


def atom(value: str) -> atom_cls:
    try:
        return atom_cls(value)
    except MalformedAtom as exc:
        # try to add an operator in case we got a version without op
        try:
            return atom_cls("=" + value)
        except MalformedAtom:
            raise exc


argparser = ArgumentParser(
    description=__doc__,
    prog=__name__,
    script=(__file__, __name__),
    config=False,
    domain=False,
)
group = argparser.add_mutually_exclusive_group()
group.add_argument(
    "-F",
    "--format",
    nargs="+",
    metavar=("FORMAT", "ATOM"),
    help="Custom output format",
    docs="""
        Specify a custom  output  format.

        Conversion specifiers start with a ``%`` symbol and are followed by
        either ``{`` or ``[``.  Next is the name of the field to expand,
        followed by a matching ``}`` or ``]``.

        The difference between ``{`` and ``[`` is that the latter is only
        printed if the field referred is set, while the former prints
        ``<unset>`` in that case.

        The following fields are supported:

        CATEGORY
            The category of the package.

        PACKAGE
            The package name.

        VERSION
            The package version without the ebuild revision.

        FULLVER
            The package name, version and revision when not zero. Thus, a zero
            revision ``-r0`` is not printed.

        REVISION
            The ebuild revision.

        SLOT
            The package slot, if exists in atom, otherwise empty.

        SUBSLOT
            The package sub slot, if exists in atom, otherwise empty.

        REPO_ID
            The package repository.

        OP
            The package prefixes, that is version specifiers.
    """,
)
group.add_argument(
    "-c", "--compare", nargs=2, metavar="ATOM", type=atom, help="Compare two atoms"
)


def _transform_format(atom: atom_cls, match: re.Match):
    if res := getattr(atom, match.group(0)[2:-1].lower()):
        return str(res)
    return "<unset>" if match.group(0)[1] == "{" else ""


@argparser.bind_main_func
def main(options, out, err):
    if options.format:
        fmt, *atoms = options.format
        VAR_REGEX = re.compile(r"%\[.+?\]|%\{.+?\}")
        for value in atoms:
            try:
                value = atom(value)
            except MalformedAtom as exc:
                err.write(f"malformed atom: {value!r}: {exc}")
                continue
            try:
                out.write(VAR_REGEX.sub(partial(_transform_format, value), fmt).strip())
            except AttributeError:
                err.write(f"bad format: {fmt!r}")
                return 1
    # TODO: check implementation and add tests
    elif options.compare:  # pragma: no cover
        atom1, atom2 = options.compare
        if atom1.unversioned_atom != atom2.unversioned_atom or atom1.slot != atom2.slot:
            op = "!="
        elif atom1 > atom2:
            op = ">"
        elif atom1 < atom2:
            op = "<"
        elif atom1 == atom2:
            op = "=="
        else:
            op = "!="
        out.write(f"{atom1} {op} {atom2}")
