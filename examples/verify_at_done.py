#!/usr/bin/env python3

"""Go over all open stabilization or keywording bugs, and check for done bugs."""

import os
import sys

from pkgcore.bugzilla import Bug, BugQuery, Component, FlagStatus
from pkgcore.bugzilla.apikey import BugzillaClientArgs
from pkgcore.ebuild.keywording import PackageListDoneAlready, PackageMatchException
from pkgcore.util.commandline import ArgumentParser, Tool

argparser = ArgumentParser(version=False, description=__doc__)
BugzillaClientArgs.mangle_argparser(argparser)

QUERY = (
    BugQuery.component(Component.STABILIZATION, Component.KEYWORDING)
    & BugQuery.unresolved()
    & BugQuery.flag("sanity-check", FlagStatus.GRANTED)
)


@argparser.bind_final_check
def check_args(parser, namespace):
    # a request is resolved against one repo: the one being worked in
    cwd = os.getcwd()
    repo = namespace.domain.find_repo(cwd, config=namespace.config, configure=False)
    if repo is None:
        parser.error(f"not inside an ebuild repository: {cwd}")
    namespace.repo = repo


def remaining_arches(repo, bug: Bug) -> set[str]:
    try:
        return {
            arch
            for _, keywords in bug.match_packages(repo, only_new=True)
            for arch in keywords
        }
    except PackageListDoneAlready:
        # every package is keyworded already, so nobody is waiting on anything
        return set()


@argparser.bind_main_func
def main(options, out, err):
    for bug in options.bugzilla.search(QUERY).values():
        if not (cc_arches := bug.arches(options.repo.known_arches)):
            continue
        try:
            remaining = remaining_arches(options.repo, bug)
        except PackageMatchException as exc:
            # a bug nobody can resolve as written says nothing about being done
            err.write(err.fg("red"), f">>> bug {bug.id}: {exc}", err.reset)
            continue

        for arch in cc_arches:
            if arch not in remaining:
                out.write(
                    out.fg("yellow"),
                    f"{bug.url}, cc: {arch}, all packages are done",
                    out.reset,
                    " -> ",
                    f"nattka resolve -a {arch} {bug.id}",
                )
                out.write("  bug summary: ", bug.summary)


if __name__ == "__main__":
    sys.exit(Tool(argparser)())
