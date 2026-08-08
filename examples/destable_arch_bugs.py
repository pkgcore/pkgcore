#!/usr/bin/env python3

"""Go over all open stabilization bugs for that arch, and drop the arch."""

import sys

from pkgcore.bugzilla import (
    BugQuery,
    BugUpdate,
    Component,
    ListChange,
    NewComment,
    Status,
)
from pkgcore.bugzilla.apikey import BugzillaClientArgs
from pkgcore.util import commandline

argparser = commandline.ArgumentParser(version=False, description=__doc__)
BugzillaClientArgs.mangle_argparser(argparser)
argparser.add_argument(
    "--arch",
    metavar="ARCH",
    required=True,
    help="The arch to check for",
    docs="""
        The arch to check for. This tool will look for all open stabilization
        bugs with that arch in the CC field, and remove it. If that was the last
        arch in the CC field, the bug will be closed as well.
    """,
)


@argparser.bind_final_check
def check_args(parser, namespace):
    repo = namespace.domain.ebuild_repos_raw
    namespace.known_arches = frozenset().union(*(pkg.known_arches for pkg in repo))

    if namespace.arch not in namespace.known_arches:
        parser.error(f"unknown arch: {namespace.arch}")


def destable(arch: str, last: bool) -> BugUpdate:
    """Drop the arch from CC, closing the bug if it was the only one left"""
    uncc = ListChange.removing(f"{arch}@gentoo.org")
    comment = f"Arch {arch} is destabled, removing."
    if last:
        return BugUpdate.resolve(
            comment=f"{comment}\n\nNo remaining arches, closing the bug.", cc=uncc
        )
    return BugUpdate(status=Status.IN_PROGRESS, cc=uncc, comment=NewComment(comment))


@argparser.bind_main_func
def main(options, out, err):
    query = (
        BugQuery.component(Component.STABILIZATION)
        & BugQuery.unresolved()
        & BugQuery.cc(f"{options.arch}@gentoo.org")
    )
    bugs = options.bugzilla.search(query)
    for i, bug in enumerate(bugs.values(), start=1):
        out.write(f"[{i}/{len(bugs)}] {bug.url}")
        out.flush()

        remaining = set(bug.arches(options.known_arches)) - {options.arch}
        options.bugzilla.update(bug.id, destable(options.arch, not remaining))


if __name__ == "__main__":
    tool = commandline.Tool(argparser)
    sys.exit(tool())
