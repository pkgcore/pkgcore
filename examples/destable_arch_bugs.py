#!/usr/bin/env python3

"""Go over all open stabilization bugs for that arch, and drop the arch."""

import json
import sys
import urllib.request as urllib
from typing import TypedDict
from urllib.parse import urlencode

from pkgcore.util import commandline


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


class BugInfo(TypedDict):
    id: int
    cc: list[str]


@argparser.bind_final_check
def check_args(parser, namespace):
    repo = namespace.domain.ebuild_repos
    namespace.known_arches = frozenset().union(*(pkg.known_arches for pkg in repo))

    if namespace.arch not in namespace.known_arches:
        parser.error(f"unknown arch: {namespace.arch}")


def fetch_bugs(arch: str, api_key: str) -> tuple[BugInfo, ...]:
    params = urlencode(
        (
            ("Bugzilla_api_key", api_key),
            ("component", "Stabilization"),
            ("include_fields", "id,cc"),
            ("bug_status", "UNCONFIRMED"),
            ("bug_status", "CONFIRMED"),
            ("bug_status", "IN_PROGRESS"),
            ("cc", f"{arch}@gentoo.org"),
        )
    )
    with urllib.urlopen(
        "https://bugs.gentoo.org/rest/bug?" + params, timeout=30
    ) as response:
        return tuple(json.loads(response.read().decode("utf-8")).get("bugs", []))


def update_bug(arch: str, api_key: str, bug_id: int, to_close: bool):
    req = {
        "Bugzilla_api_key": api_key,
        "ids": [bug_id],
        "cc": {"remove": [f"{arch}@gentoo.org"]},
    }

    comment = f"Arch {arch} is destabled, removing."
    if to_close:
        req["status"] = "RESOLVED"
        req["resolution"] = "FIXED"
        comment += "\n\nNo remaining arches, closing the bug."
    else:
        req["status"] = "IN_PROGRESS"
    req["comment"] = {"body": comment}

    data = json.dumps(req).encode("utf-8")
    url = f"https://bugs.gentoo.org/rest/bug/{bug_id}"
    request = urllib.Request(url, data=data, method="PUT")
    request.add_header("Content-Type", "application/json")
    with urllib.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


@argparser.bind_main_func
def main(options, out, err):
    for bug in fetch_bugs(options.arch, options.api_key):
        cc = frozenset(bug["cc"])
        cc_names = frozenset(
            x.split("@", 1)[0] for x in cc if x.endswith("@gentoo.org") or "@" not in x
        )
        bug_arches = cc_names.intersection(options.known_arches)

        update_bug(
            arch=options.arch,
            api_key=options.api_key,
            bug_id=bug["id"],
            to_close=len(bug_arches) == 1,
        )


if __name__ == "__main__":
    tool = commandline.Tool(argparser)
    sys.exit(tool())
