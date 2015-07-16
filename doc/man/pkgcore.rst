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
current portage configuration.

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
  PORTDIR_OVERLAY settings in make.conf are not respected anymore.

  In addition, not all fields that portage supports are used by pkgcore.
  Currently in repo sections the only supported fields are 'location',
  'priority', 'sync-type', and 'sync-uri' while 'main-repo' is the only
  supported field in the default section. Support for more attributes will be
  added in the future, but pkgcore is unlikely to ever support the full set
  used by portage.

* /etc/portage/make.conf

  Config values are only loaded from /etc/portage/make.conf, the deprecated
  /etc/make.conf location is not checked anymore.

* FEATURES="preserve-libs"

  Libraries *are not* preserved when sonames change during upgrades or
  downgrades. This can easily render systems unworkable if major core system
  library changes occur. Users will have to make use of revdep-rebuild(1) from
  portage until an equivalent is added to pkgcore and/or support for preserved
  libs is added.

  Note that this also means there is no preserved-rebuild package set support
  either.

* dynamic deps

  Dependency data for installed packages is always pulled from the vdb which is
  only allowed to be altered on install and removed at uninstall. There is no
  plan to support retrieving updated dependency data from unbuilt ebuilds in
  source repositories and updating the vdb.

Utilities
=========

**pclonecache(1)**
  clone a repository cache

**pebuild(1)**
    low-level ebuild operations, go through phases manually

**pinspect(1)**
    generic utility for inspecting repository related info

**pmaint(1)**
    generic utility for repository maintenance (syncing, copying...)

**pmerge(1)**
    generic utility for doing resolution, fetching, merging/unmerging, etc.

**pquery(1)**
    generic utility for querying info about repositories, revdeps, pkg search,
    vdb search, etc.

Reporting Bugs
==============

Please submit an issue via github:

https://github.com/pkgcore/pkgcore/issues

You can also stop by #pkgcore on freenode.

See Also
========

portage(5), make.conf(5)
