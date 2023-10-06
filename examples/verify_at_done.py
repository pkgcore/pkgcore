#!/usr/bin/env python3

"""Go over all open stabilization or keywording bugs, and check for done bugs."""

import json
import sys
import urllib.request as urllib
from typing import TypedDict
from urllib.parse import urlencode

from pkgcore.util import commandline
from pkgcore.ebuild.atom import atom
from pkgcore.ebuild.errors import MalformedAtom


argparser = commandline.ArgumentParser(version=False, description=__doc__)
argparser.add_argument(
    "--api-key",
    metavar="KEY",
    required=True,
    help="Bugzilla API key",
    docs="""
        The Bugzilla API key to use for authentication. Used mainly to overcome
        rate limiting done by bugzilla server. This tool doesn't perform any
        bug editing, just fetching info for the bug.
    """,
)


class BugInfo(TypedDict):
    id: int
    cf_stabilisation_atoms: str
    component: str
    cc: list[str]


@argparser.bind_final_check
def check_args(parser, namespace):
    namespace.repo = namespace.domain.ebuild_repos


def fetch_bugs() -> tuple[BugInfo, ...]:
    params = urlencode(
        (
            ("component", "Stabilization"),
            ("component", "Keywording"),
            (
                "include_fields",
                "id,cf_stabilisation_atoms,component,cc",
            ),
            ("bug_status", "UNCONFIRMED"),
            ("bug_status", "CONFIRMED"),
            ("bug_status", "IN_PROGRESS"),
            ("f1", "flagtypes.name"),
            ("o1", "anywords"),
            ("v1", "sanity-check+"),
        )
    )
    with urllib.urlopen(
        "https://bugs.gentoo.org/rest/bug?" + params, timeout=30
    ) as response:
        return tuple(json.loads(response.read().decode("utf-8")).get("bugs", []))


def parse_atom(pkg: str):
    try:
        return atom(pkg)
    except MalformedAtom as exc:
        try:
            return atom(f"={pkg}")
        except MalformedAtom:
            raise exc


def collect_packages(repo, bug: BugInfo):
    return tuple(
        pkg
        for a in bug["cf_stabilisation_atoms"].splitlines()
        if (b := " ".join(a.split()))
        for pkg in repo.itermatch(parse_atom(b.split(" ", 1)[0]))
    )


@argparser.bind_main_func
def main(options, out, err):
    for bug in fetch_bugs():
        try:
            pkgs = collect_packages(options.repo, bug)
            if not pkgs:
                continue
            for cc in bug["cc"]:
                cc = cc.removesuffix("@gentoo.org")
                if all(cc in pkg.keywords for pkg in pkgs):
                    out.write(
                        out.fg("yellow"),
                        f"https://bugs.gentoo.org/{bug['id']}, cc: {cc}, all packages are done",
                        out.reset,
                        " -> ",
                        f"nattka resolve -a {cc} {bug['id']}",
                    )
                if bug["component"] == "Keywording" and all(
                    f"~{cc}" in pkg.keywords for pkg in pkgs
                ):
                    out.write(
                        out.fg("yellow"),
                        f"https://bugs.gentoo.org/{bug['id']}, cc: ~{cc}, all packages are done",
                        out.reset,
                        " -> ",
                        f"nattka resolve -a {cc} {bug['id']}",
                    )
        except MalformedAtom as exc:
            err.write(
                err.fg("red"),
                f">>> Malformed bug {bug['id']} with atoms: {', '.join(bug['cf_stabilisation_atoms'].splitlines())}",
                err.reset,
                str(exc),
            )


if __name__ == "__main__":
    tool = commandline.Tool(argparser)
    sys.exit(tool())
