#!/usr/bin/env python3

"""Go over all open stabilization or keywording bugs, and check for done bugs."""

import sys

from pkgcore.bugzilla import (
    BugCategory,
    BugQuery,
    BugzillaError,
    Component,
    FlagStatus,
)
from pkgcore.bugzilla.apikey import BugzillaClientArgs
from pkgcore.bugzilla.pkglist import ALL_KEYWORDS, NO_KEYWORDS, SAME_KEYWORDS
from pkgcore.util import commandline

argparser = commandline.ArgumentParser(version=False, description=__doc__)
BugzillaClientArgs.mangle_argparser(argparser)

QUERY = (
    BugQuery.component(Component.STABILIZATION, Component.KEYWORDING)
    & BugQuery.unresolved()
    & BugQuery.flag("sanity-check", FlagStatus.GRANTED)
)

UNEXPANDED = frozenset((ALL_KEYWORDS, SAME_KEYWORDS))


@argparser.bind_final_check
def check_args(parser, namespace):
    namespace.repo = namespace.domain.ebuild_repos_raw
    namespace.known_arches = frozenset().union(
        *(repo.known_arches for repo in namespace.repo)
    )


def requested_arches(entry, cc_arches):
    """The arches a package list line asks for.

    A line carrying no keywords of its own inherits the whole CC list, which is
    how nattka reads it too.
    """
    keywords = frozenset(x.lstrip("~") for x in entry.keywords)
    if NO_KEYWORDS in keywords:
        return frozenset()
    return keywords or frozenset(cc_arches)


def pending_packages(repo, bug, cc_arches):
    """Map each requested arch to the packages it still has to stabilize.

    Returns None when the bug can't be judged, either because an atom matches
    nothing in the repo or because the package list still holds unexpanded
    keyword shorthands. Concluding from a partial view is how an arch gets told
    it is done while a package the repo never matched is still waiting on it.
    """
    pending: dict[str, list] = {}
    for entry in bug.package_list.entries:
        if entry.pkg is None:
            continue
        if UNEXPANDED & frozenset(entry.keywords):
            return None
        if not (pkgs := tuple(repo.itermatch(entry.pkg))):
            return None
        for arch in requested_arches(entry, cc_arches):
            pending.setdefault(arch, []).extend(pkgs)
    return pending


@argparser.bind_main_func
def main(options, out, err):
    for bug in options.bugzilla.search(QUERY).values():
        # the heuristic for keywording is wrong, skip those for now
        if bug.category is BugCategory.KEYWORDREQ:
            continue
        cc_arches = bug.arches(options.known_arches)
        try:
            pending = pending_packages(options.repo, bug, cc_arches)
        except BugzillaError as exc:
            err.write(err.fg("red"), f">>> {exc}", err.reset)
            continue
        if not pending:
            continue

        for arch in cc_arches:
            if not (pkgs := pending.get(arch)):
                continue
            if all(arch in pkg.keywords for pkg in pkgs):
                out.write(
                    out.fg("yellow"),
                    f"{bug.url}, cc: {arch}, all packages are done",
                    out.reset,
                    " -> ",
                    f"nattka resolve -a {arch} {bug.id}",
                )


if __name__ == "__main__":
    tool = commandline.Tool(argparser)
    sys.exit(tool())
