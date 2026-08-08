#!/usr/bin/env python3

"""Assign bug-wrangler owned keywording and stabilization bugs to maintainers."""

import sys

from pkgcore.bugzilla import (
    BugCategory,
    BugQuery,
    BugUpdate,
    BugzillaError,
    ListChange,
)
from pkgcore.bugzilla.apikey import BugzillaClientArgs
from pkgcore.bugzilla.changes import MAINTAINER_NEEDED
from pkgcore.util import commandline

argparser = commandline.ArgumentParser(color=False, version=False, description=__doc__)
BugzillaClientArgs.mangle_argparser(argparser)

QUERY = (
    BugQuery.assigned_to("bug-wranglers")
    & BugQuery.category(BugCategory.STABLEREQ, BugCategory.KEYWORDREQ)
    & BugQuery.unresolved()
)


@argparser.bind_final_check
def check_args(parser, namespace):
    # raw, so packages the profile filters out still yield their maintainers
    namespace.repo = namespace.domain.ebuild_repos_raw


def collect_maintainers(repo, bug):
    for a in bug.package_list.atoms:
        for pkg in repo.itermatch(a.unversioned_atom):
            for maintainer in pkg.maintainers:
                yield maintainer.email


@argparser.bind_main_func
def main(options, out, err):
    for bug in options.bugzilla.search(QUERY).values():
        if not bug.package_list:
            continue
        try:
            maintainers = dict.fromkeys(collect_maintainers(options.repo, bug)) or (
                MAINTAINER_NEEDED,
            )
            assignee, *add_cc = maintainers
            changes = options.bugzilla.update(
                bug.id,
                BugUpdate(assigned_to=assignee, cc=ListChange.adding(*add_cc)),
            )
            out.write(f"Bug: {bug.id}, assigned to {assignee}, changed: {changes!r}")
        except BugzillaError as exc:
            err.write(err.fg("red"), f"Bug {bug.id}: {exc}", err.reset)


if __name__ == "__main__":
    tool = commandline.Tool(argparser)
    sys.exit(tool())
