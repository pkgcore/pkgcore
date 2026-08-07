#!/usr/bin/env python3
# Copyright 2007 Charlie Shepherd

import sys

try:
    from pkgcore.repository.util import get_raw_repos, get_virtual_repos
    from pkgcore.util import commandline
except ImportError:
    print("Cannot import pkgcore!", file=sys.stderr)
    print(
        "Verify it is properly installed and/or PYTHONPATH is set correctly.",
        file=sys.stderr,
    )
    if "--debug" not in sys.argv:
        print("Add --debug to the commandline for a traceback.", file=sys.stderr)
    else:
        raise
    sys.exit(1)


argparser = commandline.ArgumentParser(color=False, version=False)
argparser.add_argument(
    "-r",
    "--repo",
    action=commandline.StoreRepoObject,
    help="repo to give info about (default from domain if omitted)",
)


@argparser.bind_final_check
def check_args(parser, namespace):
    # Get repo(s) to operate on.
    if namespace.repo:
        repos = (namespace.repo,)
    else:
        repos = namespace.domain.repos
    namespace.repos = get_virtual_repos(get_raw_repos(repos), False)


@argparser.bind_main_func
def main(options, out, err):
    for repo in options.repos:
        out.write(f"Repo ID: {repo.repo_id}")
        location = getattr(repo, "location", None)
        if location:
            out.write(f"Repo location: {location}")
        else:
            out.write("Repo has no on-disk location")
        out.write(f"{len(repo.versions)} packages")
        out.write(f"{len(repo.packages)} categories")
        out.write()


if __name__ == "__main__":
    tool = commandline.Tool(argparser)
    sys.exit(tool())
