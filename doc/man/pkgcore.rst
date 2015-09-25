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

Atom Syntax
===========

pkgcore supports an extended form of atom syntax- examples are provided below.

This form can be used in configuration files, but in doing so portage will have
issues with the syntax, so if you want to maintain configuration
compatibility, limit your usage of the extended syntax to the commandline only.

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

Additionally, pkgcore supports additional atom extensions that are more
'pure' to the atom specification.

Use Dep atoms
-------------

http://bugs.gentoo.org/2272 has the details, but a use dep atom is basically a
normal atom that is able to force/disable flags on the target atom.  Portage
currently doesn't support use deps, although pkgcore and paludis do.

Note: Although paludis supports use deps, the syntax is different to what
pkgcore uses.

Syntax:

  normal-atom[enabled_flag1,enabled_flag2,-disabled_flag,-disabled_flag2]

Example:

  sys-apps/portage[build]

Would only match sys-apps/portage with the build flag forced on.

Forcing 'build' off while forcing 'doc' on would be:

  sys-apps/portage[-build,doc]

Slot dep atoms
--------------

Slot dep atoms allow for finer grained matching of packages- portage as of
2.1.2 supports them, but they're currently unable to be used in the tree.

Syntax:

  normal-atom:slot1,slot2,slot3

Matching just python in slot '2.3':

  dev-lang/python:2.3

Matching python in slot '2.3' or '2.4'

  dev-lang/python:2.3,2.4

repo_id atoms
-------------

The main usage of this form is to limit an atom to match only within a specific
repository - for example, to state "I need python from the gentoo-x86
repository _only_"

syntax:

  normal-atom::repository-id

Example:

  sys-devel/gcc::gentoo

A complication of this form is that ':' is also used for slots- '::' is treated
as strictly repository id matching, and must be the last token in the atom.

If you need to do slot matching in addition, it would be

  sys-devel/gcc:3.3::gentoo

which would match slot '3.3' from repository 'gentoo' (defined in
profiles/repo_name) of sys-devel/gcc.

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
