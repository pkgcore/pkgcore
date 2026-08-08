"""Locating a bugs.gentoo.org api key, and wiring it into an argparser.

:func:`find_api_key` consults four sources in order, stopping at the first one
holding a non-empty value:

1. an explicit key, normally from ``--api-key``.  Convenient, but visible to
   anyone able to read ``ps``.
2. the ``BUGZ_API_KEY`` environment variable.  The only source usable from CI
   without writing a secret to disk.
3. ``~/.bugzrc``, an INI file whose name and layout come from pybugz.  The
   sections ``default``, ``gentoo`` and ``Gentoo`` are tried in that order::

       [default]
       key = AbCdEf0123456789AbCdEf0123456789AbCdEf01

   Only the ``key`` option is read, so an existing pybugz config works as is.

4. ``~/.bugz_token``, holding nothing but the key::

       AbCdEf0123456789AbCdEf0123456789AbCdEf01

Either file being group or world readable is warned about, but still used.

Finding no key at all is not an error.  The client then runs anonymously, which
is read only, and which Bugzilla further degrades by truncating every email
address it returns at the ``@``.
"""

__all__ = (
    "API_KEY_ENV",
    "BugzillaApiKey",
    "BugzillaClientArgs",
    "find_api_key",
)

import os
import stat
import typing
from configparser import ConfigParser
from configparser import Error as ConfigParserError
from pathlib import Path

from ..log import logger
from .client import DEFAULT_URL, Bugzilla
from .errors import BugzillaUsageError

API_KEY_ENV: typing.Final = "BUGZ_API_KEY"

_RC_FILE: typing.Final = ".bugzrc"
_RC_SECTIONS: typing.Final = ("default", "gentoo", "Gentoo")
_TOKEN_FILE: typing.Final = ".bugz_token"

API_KEY_DOCS: typing.Final = """
    The Bugzilla API key to use for authentication.  WARNING: passing the key
    here exposes it to every other user of the system, via ``ps``; prefer one
    of the other sources below.

    Four sources are consulted in order, and the first non-empty one wins:

    1. this option
    2. the ``BUGZ_API_KEY`` environment variable
    3. ``~/.bugzrc``, an INI file, looking at the ``default``, ``gentoo`` and
       ``Gentoo`` sections in that order::

           [default]
           key = AbCdEf0123456789AbCdEf0123456789AbCdEf01

       Only ``key`` is read, so an existing pybugz config can be left alone.

    4. ``~/.bugz_token``, holding nothing but the key::

           AbCdEf0123456789AbCdEf0123456789AbCdEf01

    A warning is emitted if either file is group or world readable.

    Without a key the client is read only, and Bugzilla truncates every email
    address it returns at the ``@``.
"""


def _warn_if_readable(path: Path) -> None:
    try:
        mode = path.stat().st_mode
    except OSError:
        return
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        logger.warning("%s holds an api key and is readable by others", path)


def find_api_key(
    explicit: str | None = None, *, allow_env: bool = True, home: Path | None = None
) -> str | None:
    """Locate an api key, per the precedence documented for this module.

    :param explicit: a key supplied directly, normally from ``--api-key``;
        blank or whitespace-only is treated as absent
    :param allow_env: whether ``$BUGZ_API_KEY`` may be consulted
    :param home: directory to look the dotfiles up in, defaulting to the
        user's home
    :return: the key, or None to run anonymously
    :raises BugzillaUsageError: if ``~/.bugzrc`` exists but can't be parsed
    """
    if explicit and (explicit := explicit.strip()):
        return explicit
    if allow_env and (key := os.environ.get(API_KEY_ENV, "").strip()):
        return key
    home = home or Path.home()
    if (rc := home / _RC_FILE).is_file():
        _warn_if_readable(rc)
        config = ConfigParser(default_section=_RC_SECTIONS[0])
        try:
            config.read(rc)
        except (ConfigParserError, OSError, UnicodeDecodeError) as exc:
            raise BugzillaUsageError(f"failed parsing {rc}: {exc}") from exc
        for section in _RC_SECTIONS:
            if config.has_option(section, "key") and (
                key := config.get(section, "key").strip()
            ):
                return key
    if (token := home / _TOKEN_FILE).is_file():
        _warn_if_readable(token)
        if key := token.read_text().strip():
            return key
    return None


class BugzillaApiKey:
    """Adds ``--api-key``, defaulting through :func:`find_api_key`"""

    @classmethod
    def mangle_argparser(cls, parser: typing.Any) -> None:
        parser.add_argument(
            "--api-key", metavar="TOKEN", help="Bugzilla API key", docs=API_KEY_DOCS
        )
        parser.bind_delayed_default(1000, "api_key")(cls._default_api_key)

    @staticmethod
    def _default_api_key(namespace: typing.Any, attr: str) -> None:
        setattr(namespace, attr, find_api_key())


class BugzillaClientArgs(BugzillaApiKey):
    """As :class:`BugzillaApiKey`, plus ``--bugzilla-url`` and a ready client.

    The client lands on ``namespace.bugzilla``; its delayed default runs after
    the key's, so the key is resolved by the time it is built.
    """

    @classmethod
    def mangle_argparser(cls, parser: typing.Any) -> None:
        super().mangle_argparser(parser)
        parser.add_argument(
            "--bugzilla-url",
            metavar="URL",
            default=DEFAULT_URL,
            help="base URL of the Bugzilla instance",
        )
        parser.bind_delayed_default(1001, "bugzilla")(cls._default_client)

    @staticmethod
    def _default_client(namespace: typing.Any, attr: str) -> None:
        setattr(
            namespace,
            attr,
            Bugzilla(
                namespace.api_key,
                base_url=getattr(namespace, "bugzilla_url", DEFAULT_URL),
            ),
        )
