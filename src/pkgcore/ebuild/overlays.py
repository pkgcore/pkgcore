"""Support for Gentoo's published list of ebuild repositories.

``repositories.xml`` maps a repository name to the URIs it can be synced from.
This module fetches and caches that list, and writes repos.conf entries for the
repos picked out of it, which is what ``pmaint sync --import`` is built on.
"""

__all__ = (
    "FALLBACK_REPOS_BASE",
    "RemoteRepo",
    "RemoteRepoError",
    "add_repos_conf_entry",
    "configured_repos",
    "remote_repos",
    "repo_masters",
    "repos_base",
)

import configparser
import os
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass
from email.utils import formatdate
from os.path import join as pjoin

from lxml import etree
from snakeoil.fileutils import AtomicWriteFile, readfile_ascii

from .. import const
from ..exceptions import PkgcoreUserException
from ..fs.livefs import sorted_scan
from ..log import logger
from .portage_conf import ParseConfig
from .repo_objs import RepoConfig

REPOSITORIES_XML_URI = "https://api.gentoo.org/overlays/repositories.xml"
# where new repos go when the config gives nothing better to go on
FALLBACK_REPOS_BASE = "/var/db/repos"

# repositories.xml source types mapped onto the syncer that handles them; types
# missing here have no pkgcore syncer to drive them.
_SYNC_TYPES = {
    "bzr": "bzr",
    "git": "git",
    "mercurial": "hg",
    "rsync": "rsync",
    "svn": "svn",
}


class RemoteRepoError(PkgcoreUserException):
    """Failure while using the remote repository list."""


@dataclass(slots=True, frozen=True)
class RemoteRepo:
    """A repository as described by the remote list."""

    name: str
    homepage: str
    # (sync-type, sync-uri) pairs in the order the list gives them, which is
    # the order upstream prefers them in
    sources: tuple[tuple[str, str], ...]


def _cache_path() -> str:
    # the user cache even when running as root, since that's where pkgcore's
    # own stub config keeps repos and what CI images cache between runs
    return pjoin(const.USER_CACHE_PATH, "repositories.xml")


def _fetch(uri: str, dest: str) -> None:
    """Refresh the cached copy of the repository list."""
    headers = {}
    etag_path = dest + ".etag"
    try:
        mtime = os.stat(dest).st_mtime
    except FileNotFoundError:
        cached = False
    else:
        cached = True
        headers["If-Modified-Since"] = formatdate(mtime, usegmt=True)
        if etag := readfile_ascii(etag_path, none_on_missing=True):
            headers["If-None-Match"] = etag.strip()

    req = urllib.request.Request(uri, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req) as resp:
            data = resp.read()
            etag = resp.getheader("ETag")
    except urllib.error.URLError as e:
        if getattr(e, "code", None) == 304:  # not modified
            logger.debug("repository list is unchanged")
            return
        if not cached:
            raise RemoteRepoError(f"failed fetching {uri!r}: {e.reason}") from e
        logger.warning("failed fetching %r: %s; using cached copy", uri, e.reason)
        return

    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with AtomicWriteFile(dest, binary=True, perms=0o644) as f:
            f.write(data)
        if etag:
            with AtomicWriteFile(etag_path, perms=0o644) as f:
                f.write(etag.strip())
    except OSError as e:
        raise RemoteRepoError(f"failed caching {dest!r}: {e.strerror}") from e


def remote_repos() -> dict[str, RemoteRepo]:
    """Every repo in the remote list, keyed by name."""
    path = _cache_path()
    _fetch(REPOSITORIES_XML_URI, path)

    try:
        root = etree.parse(path).getroot()
    except (OSError, etree.XMLSyntaxError) as e:
        raise RemoteRepoError(f"failed parsing {path!r}: {e}") from e

    return {
        name: RemoteRepo(
            name=name,
            homepage=(el.findtext("homepage") or "").strip(),
            sources=tuple(
                (sync_type, uri)
                for source in el.findall("source")
                if (sync_type := _SYNC_TYPES.get(source.get("type")))
                and (uri := (source.text or "").strip())
            ),
        )
        for el in root.findall("repo")
        if (name := (el.findtext("name") or "").strip())
    }


def configured_repos(path: str) -> dict[str, dict[str, str]]:
    """Every repo declared under a repos.conf path, keyed by name.

    Locations are resolved the way :py:class:`PortageConfig` resolves them, so
    that they can be compared against one another.
    """
    parser = ParseConfig()
    repos: dict[str, dict[str, str]] = {}
    for fp in sorted_scan(
        os.path.realpath(path), follow_symlinks=True, hidden=False, backup=False
    ):
        try:
            with open(fp) as f:
                _defaults, sections = parser.parse_file(f)
        except (OSError, configparser.Error) as e:
            raise RemoteRepoError(f"failed parsing {fp!r}: {e}") from e
        for name, settings in sections.items():
            if location := settings.get("location"):
                location = os.path.expanduser(location)
                if not os.path.isabs(location):
                    # relative paths are based on where repos.conf is located
                    location = os.path.abspath(pjoin(os.path.dirname(path), location))
                settings["location"] = location
            repos[name] = settings
    return repos


def repo_masters(location: str) -> tuple[str, ...]:
    """Repos that the one at a given location inherits from."""
    return RepoConfig(location).masters


def repos_base(configured: dict[str, dict[str, str]]) -> str:
    """Where a new repo belongs, going by the repos already being synced.

    That's /var/db/repos on an ordinary install, but pkgcore's stub config keeps
    repos under the user cache instead, and an import should follow whichever is
    in use rather than scatter repos across both.
    """
    dirs = Counter(
        os.path.dirname(settings["location"])
        for settings in configured.values()
        if settings.get("location") and settings.get("sync-uri")
    )
    if common := dirs.most_common(1):
        return common[0][0]
    return FALLBACK_REPOS_BASE


def add_repos_conf_entry(
    path: str, name: str, location: str, sync_type: str, sync_uri: str
) -> str:
    """Declare a repo under a repos.conf path, returning the file written to.

    A repos.conf directory gets a file per repo so that dropping the repo later
    is a matter of dropping its file.
    """
    entry = (
        f"[{name}]\n"
        f"location = {location}\n"
        f"sync-type = {sync_type}\n"
        f"sync-uri = {sync_uri}\n"
    )
    try:
        if os.path.isfile(path):
            dest = path
            # keep the new section off the tail of the previous one
            with open(dest) as f:
                separator = "" if f.read().endswith("\n\n") else "\n"
            with open(dest, "a") as f:
                f.write(separator + entry)
        else:
            os.makedirs(path, exist_ok=True)
            dest = pjoin(path, f"{name}.conf")
            with AtomicWriteFile(dest, perms=0o644) as f:
                f.write(entry)
    except OSError as e:
        raise RemoteRepoError(
            f"failed writing {name!r} to {path!r}: {e.strerror}"
        ) from e
    return dest
