=======
pkgcore
=======

Description
===========

pkgcore is a framework for package management; via the appropriate class
plugins, the design should allow for almost any underlying repository, config,
or format to be used. However, it's currently focused on providing support for
ebuilds and the Gentoo ecosystem in general.

Portage Compatibility
=====================

In general, pkgcore tries to remain somewhat compatible with much of the
current **portage**\(5) configuration.

Missing or differing functionality
----------------------------------

The following is a list of semi-major portage features that currently do not
have a pkgcore equivalent. Some of them are planned to be added in the future
while others are not (and are noted as such).

This section mostly serves as a warning for the unwary that might expect
everything to operate in the same fashion when switching between package
managers.

* /etc/portage/repos.conf

  The only way to add repos to pkgcore is to use repos.conf, PORTDIR and
  PORTDIR_OVERLAY settings in **make.conf**\(5) are not respected anymore.

  In addition, not all fields that portage supports are used by pkgcore.
  Currently in repo sections the only supported fields are 'location',
  'priority', 'sync-type', and 'sync-uri' while 'main-repo' is the only
  supported field in the default section. Support for more attributes will be
  added in the future, but pkgcore is unlikely to ever support the full set
  used by portage.

* /etc/portage/make.conf

  Config values are only loaded from /etc/portage/make.conf, the deprecated
  /etc/make.conf location is not checked anymore.

* dynamic deps

  Dependency data for installed packages is always pulled from the vdb which is
  only allowed to be altered on install and removed at uninstall. There is no
  plan to support retrieving updated dependency data from unbuilt ebuilds in
  source repositories and updating the vdb.

FEATURES
--------

Supported:

* ccache
* distcc
* sandbox
* usersandbox
* userpriv
* test
* nodoc
* noinfo
* noman
* userfetch (forced on)
* usersync
* collision-protect
* metadata-transfer (does not do the actual transfer however)
* nostrip

Partially supported:

* strict (mostly there, just missing a few additions)

Unsupported digest-related:

* assume-digests
* cvs
* digest

Unsupported misc:

* severe
* keeptemp
* keepwork
* distlocks
* selinux
* sesandbox (selinux context sandbox)
* fixpackages
* notitles

Unsupported, unlikely to be implemented:

* noauto  (too tool-specific)
* mirror

  It's possible to implement it via a custom fetcher, but there are better
  ways; use ``mirror-dist`` if you want a mirror.

* lmirror (same)
* preserve-libs

  Libraries *are not* preserved when sonames change during upgrades or
  downgrades. This can easily render systems unworkable if major core system
  library changes occur. Users will have to make use of ``revdep-rebuild(1)`` from
  portage until an equivalent is added to pkgcore and/or support for preserved
  libs is added.

  Note that this also means there is no preserved-rebuild package set support
  either.

Aside from that... everything else make.conf wise should be supported with
out issue- if not, please open an issue.

For ``/etc/portage/``, we don't support modules (define custom cache modules)
due the fact our cache subsystem has grown a bit beyond what got imported into
Portage in 2.1.

For ``/etc/portage/package.*`` files, we support an extended atom syntax which
can be used in place of normal atoms (It goes without saying Portage doesn't
support the extension yet, thus introducing incompatibility if used) - read
extended-atom-syntax.rst for the details.

Configuration
=============

Note for Portage users
----------------------

If you already know how to configure Portage you can probably just skip this
section. As long as you do not have an ``/etc/pkgcore/pkgcore.conf`` or
``~/.config/pkgcore/pkgcore.conf`` pkgcore will read Portage's configuration
files.

Basics, querying
----------------

There are multiple ways to configure pkgcore. No matter which method you pick,
the ``pconfig(1)`` utility will allow you to check if pkgcore interprets the
configuration the way you intend. Part of a configuration dump could look
like::

 $ pconfig dump
 <lots of output snipped>

 '/usr/local/portage/private' {
     # typename of this section: repo
     class pkgcore.ebuild.repository.UnconfiguredTree;
     # type: refs:cache
     cache {
         # typename of this section: cache
         class pkgcore.cache.flat_hash.database;
 <some stuff snipped>
         # type: str
         label '/usr/local/portage/private';
         # type: str
         location '/var/cache/edb/dep';
     };
     # type: list
     default_mirrors 'http://ftp.easynet.nl/mirror/gentoo//distfiles';
     # type: ref:eclass_cache
     eclass_cache 'eclass stack';
     # type: str
     location '/usr/local/portage/private';
 }
 <lots of output snipped>

Starting at the top this means there is a "repo" known to pkgcore as
"/usr/local/portage/private", of the class
"pkgcore.ebuild.repository.UnconfiguredTree". The "repo" type means it
is something containing packages. The "class" means that this
particular repo contains unbuilt ebuilds. Below that are various
parameters specific to this class. The "type" comment tells you how
the argument is interpreted (this depends on the class).

The first is "cache". This is a nested section: it defines a new
object of the type "cache", class "pkgcore.cache.flat_hash.database".
Below that are the parameters given to this cache class. It is import
to understand that the ebuild repository does not care about the exact
class of the cache. All it needs is one or more things of type
"cache". There could have been some db-based cache here for example.

The next argument to the repo is "default_mirrors" which is handled as
a list of strings. "location" is a single string.

"eclass_cache" is a section reference pointing to the named section
"eclass stack" defined elsewhere in the dump (omitted here).

If your configuration defines a section that does not show up in
dump you can use ``uncollapsable`` to figure out why::

 $ pconfig uncollapsable
 Collapsing section named 'ebuild-repo-common':
 type pkgcore.ebuild.repository.UnconfiguredTree needs settings for 'location'

 Collapsing section named 'cache-common':
 type pkgcore.cache.flat_hash.database needs settings for 'label'

Unfortunately the configuration system cannot distinguish between
sections that are only meant as a base for other sections and actual
configuration mistakes. The messages you see here are harmless. If you
are debugging a missing section you should look for "Collapsing
section named 'the-broken-section'" in the output.

Portage compatibility mode
--------------------------

If you do not have a global (``/etc/pkgcore.conf``) or local
(``~/.pkgcore.conf``) configuration file pkgcore will automatically fall back to
reading ``/etc/portage/make.conf`` and the other Portage configuration files.  A
noticable difference is pkgcore does not support picking up variables like USE
from the environment, so you can't run commands like ``USE="foo" pmerge
package``. Apart from that things should just work the way you're used to.

Beyond Portage compatibility mode
---------------------------------

Basics
~~~~~~

If you want to define extra repositories pkgcore should know about but Portage
should not you will need a minimal configuration file. Pkgcore reads two
configuration files: ``~/.pkgcore.conf`` and ``/etc/pkgcore.conf``.  Settings in
the former override the ones in the latter.

If one of them exists this completely disables Portage configuration file
parsing. The first thing you will probably want to do is re-enable that, by
putting in one of the configuration files::

 [autoload-portage]
 class=pkgcore.ebuild.portage_conf.config_from_make_conf

If you then run ``pconfig dump`` you should see among other things::

 'autoload-portage' {
    # typename of this section: configsection
    class pkgcore.ebuild.portage_conf.config_from_make_conf;
 }

Section names are usually arbitrary but sections that load extra configuration
data are an exception: they have to start with "autoload" or they will not be
processed. If you change the section name to just "portage" you will still see
it show up in ``pconfig dump`` but all other things defined in
``/etc/portage/make.conf`` will disappear.

``pconfig`` can tell you what arguments a class takes::

 $ pconfig describe_class pkgcore.config.basics.parse_config_file
 typename is configsection

 parser: callable (required)
 path: str (required)

If you wanted to remove the overlay mentioned at the top of this document from
``/etc/portage/make.conf`` but keep it available to pkgcore you would add::

 [/usr/local/portage/private]
 class=pkgcore.ebuild.repository.UnconfiguredTree
 cache=private-cache
 default_mirrors='http://ftp.easynet.nl/mirror/gentoo//distfiles'
 eclass_cache='eclass stack'
 location='/usr/local/portage/private'

 [private-cache]
 class=pkgcore.cache.flat_hash.database
 ; All the stuff snipped earlier
 label='/usr/local/portage/private'
 location='/var/cache/edb/dep'

Because the ini file format does not allow nesting sections we had to
put the cache in a named section and refer to that. The dump output
will reflect this but everything else will work just like it did
before.

Inherits
~~~~~~~~

If you have a lot of those overlays you can avoid repeating the common
bits::

 [stuff-common-to-repos]
 class=pkgcore.ebuild.repository.UnconfiguredTree
 default_mirrors='http://ftp.easynet.nl/mirror/gentoo//distfiles'
 eclass_cache='eclass stack'
 inherit-only=true

 [/usr/local/portage/private]
 inherit=stuff-common-to-repos
 location='/usr/local/portage/private'
 cache=private-cache

 [/usr/local/portage/other-overlay]
 inherit=stuff-common-to-repos
 location='/usr/local/portage/other-overlay'
 cache=other-overlay-cache

 ; And do the same thing for the caches.

There is nothing special about sections used as target for "inherit".
They can be complete sections, although they do not have to be. If
they are not complete sections you should set inherit-only to true for
them, to make pconfig uncollapsable ignore errors in them.

Actually, the Portage emulation mode uses inherit targets too, so you
could just have inherited "ebuild-repo-common". Inherit targets do not
have to live in the same file as they are inherited from.

One last special features: things marked as "incremental" get their
inherited value appended instead of overriding it.

Aliases
~~~~~~~

You may have seen something called "section_alias" in a Portage
compatibility configuration. These are used to make an existing named
section show up under a second name. You probably do not need them if
you write your own configuration.

Atom Syntax
===========

In addition to the atom specification enhancements defined in various supported
EAPIs, pkgcore provides several syntax extensions mostly relating to globbing-
examples are provided below.

This form can be used in configuration files, but in doing so portage will have
issues with the syntax. To maintain configuration compatibility, limit extended
syntax usage to the commandline only.

===================== ==========================================================
Token                 Result
===================== ==========================================================
\*                    match anything
portage               package name must be ``portage``
dev-util/*            category must be ``dev-util``
dev-\*/\*             category must start with ``dev-``, any package name
dev-util/*            category must be ``dev-util``, any package
dev-*                 package must start with ``dev-``, any category
\*cgi*                package name must have ``cgi`` in it
\*x11*/X*             category must have ``x11`` in it, package must start with ``X``
\*-apps/portage*      category must end in ``-apps``, package must start with ``portage``
dev-vcs/\*bzr*tools\* category must be dev-vcs, and the globbing there is like
                      shell globbing (bzr and tools must be in the package
                      name, and bzr must proceed tools)
=portage-1.0          match version 1.0 of any 'portage' package
===================== ==========================================================

Utilities
=========

**pclonecache**\(1)
  clone a repository cache

**pebuild**\(1)
  low-level ebuild operations, go through phases manually

**pinspect**\(1)
  generic utility for inspecting repository related info

**pmaint**\(1)
  generic utility for repository maintenance (syncing, copying...)

**pmerge**\(1)
  generic utility for doing resolution, fetching, merging/unmerging, etc.

**pquery**\(1)
  generic utility for querying info about repositories, revdeps, pkg search,
  vdb search, etc.

Reporting Bugs
==============

Please submit an issue via github:

https://github.com/pkgcore/pkgcore/issues

See Also
========

**portage**\(5), **make.conf**\(5), **pclonecache**\(1), **pebuild**\(1),
**pinspect**\(1), **pmaint**\(1), **pmerge**\(1), **pquery**\(1)
