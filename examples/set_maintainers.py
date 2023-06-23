#!/usr/bin/env python3

import json
import sys
import urllib.request as urllib
from urllib.parse import urlencode

from pkgcore.util import commandline
from pkgcore.ebuild.atom import atom
from pkgcore.ebuild.errors import MalformedAtom


argparser = commandline.ArgumentParser(color=False, version=False)
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


@argparser.bind_final_check
def check_args(parser, namespace):
    namespace.repo = namespace.domain.ebuild_repos


def fetch_bugs():
    params = urlencode(
        (
            ("assigned_to", "bug-wranglers"),
            ("component", "Stabilization"),
            ("component", "Keywording"),
            (
                "include_fields",
                "id,cf_stabilisation_atoms",
            ),
            ("bug_status", "UNCONFIRMED"),
            ("bug_status", "CONFIRMED"),
            ("bug_status", "IN_PROGRESS"),
        )
    )
    with urllib.urlopen(
        "https://bugs.gentoo.org/rest/bug?" + params, timeout=30
    ) as response:
        reply = json.loads(response.read().decode("utf-8")).get("bugs", [])
    return {
        bug["id"]: bug["cf_stabilisation_atoms"].splitlines()
        for bug in reply
        if bug["cf_stabilisation_atoms"].strip()
    }


def parse_atom(pkg: str):
    try:
        return atom(pkg)
    except MalformedAtom as exc:
        try:
            return atom(f"={pkg}")
        except MalformedAtom:
            raise exc


def collect_maintainers(repo, atoms):
    for a in atoms:
        for pkg in repo.itermatch(parse_atom(a.split(" ", 1)[0]).unversioned_atom):
            for maintainer in pkg.maintainers:
                yield maintainer.email


@argparser.bind_main_func
def main(options, out, err):
    for bug_id, atoms in fetch_bugs().items():
        try:
            maintainers = dict.fromkeys(collect_maintainers(options.repo, atoms)) or (
                "maintainer-needed@gentoo.org",
            )
            assignee, *add_cc = maintainers

            request_data = dict(
                Bugzilla_api_key=options.api_key,
                cc_add=add_cc,
                assigned_to=assignee,
            )
            request = urllib.Request(
                url=f"https://bugs.gentoo.org/rest/bug/{bug_id}",
                data=json.dumps(request_data).encode("utf-8"),
                method="PUT",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            with urllib.urlopen(request, timeout=30) as response:
                reply = response.read().decode("utf-8")
            out.write(f"Bug: {bug_id}, replied: {reply}")
        except MalformedAtom:
            err.write(
                err.fg("red"),
                f"Malformed bug {bug_id} with atoms: {', '.join(atoms)}",
                err.reset,
            )


if __name__ == "__main__":
    tool = commandline.Tool(argparser)
    sys.exit(tool())
