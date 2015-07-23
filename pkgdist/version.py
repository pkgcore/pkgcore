# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# License: BSD/GPL2

"""Version information (tied to git)."""

import errno
import os


def _run_git(cwd, cmd):
    import subprocess

    env = dict(os.environ)
    env["LC_CTYPE"] = "C"

    with open(os.devnull, 'wb') as null:
        r = subprocess.Popen(
            ['git'] + list(cmd), stdout=subprocess.PIPE, env=env,
            stderr=null, cwd=cwd)

    stdout = r.communicate()[0]
    return stdout, r.returncode


def get_git_version(cwd):
    """:return: git sha1 rev"""

    cwd = os.path.abspath(cwd)
    try:
        stdout, ret = _run_git(cwd, ["log", "--format=%H\n%ad", "HEAD^..HEAD"])

        if ret != 0:
            return {}

        data = stdout.decode("ascii").splitlines()

        return {
            "rev": data[0],
            "date": data[1],
            'tag': _get_git_tag(cwd, data[0]),
        }
    except EnvironmentError as e:
        # ENOENT is thrown when the git binary can't be found.
        if e.errno != errno.ENOENT:
            raise
        return {'rev': 'unknown', 'date': 'unknown', 'tag': 'unknown'}


def _get_git_tag(cwd, rev):
    stdout, _ = _run_git(cwd, ['name-rev', '--tag', rev])
    tag = stdout.decode("ascii").split()
    if len(tag) != 2:
        return None
    tag = tag[1]
    if not tag.startswith("tags/"):
        return None
    tag = tag[len("tags/"):]
    if tag.endswith("^0"):
        tag = tag[:-2]
    if tag.startswith("v"):
        tag = tag[1:]
    return tag
