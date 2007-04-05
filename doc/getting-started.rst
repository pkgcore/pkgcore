===============
Getting Started
===============

Portage Differences
+++++++++++++++++++

Currently portage handles all actions primarily through one script, emerge.
pkgcore breaks this functionality down into 3 scripts: ``pmerge``, ``pmaint``,
and ``pquery``.

Pmerge
======

``pmerge`` is fairly similar to ``emerge`` in most usage instances:

Basic Usage
-----------

``pmerge -us world``
  Update world; don't try to update dependencies for already installed
  packages.
``pmerge -uDs world``
  Update world, trying to update all encountered dependencies/packages.
``pmerge -p dev-util/bzrtools``
  Pretend to install bzrtools
``pmerge -C \<sys-kernel/gentoo-sources-2.6.19``
  Remove gentoo-sources less than 2.6.19
``pmerge --clean``
  Remove unused packages.

  **Warning:** This can break your system if incorrectly used. Check with
  ``--pretend`` before running it.

  Additionally, it currently defaults to identifying only what's required for
  world/system; installed packages don't require their build depends to be
  satisfied. As such, ``--clean`` will identify them for removal if they're not
  runtime depended upon.

  If you want ``--clean`` to preserve your build depends, use the ``-B``
  option.


Sets
----

Available sets are dependent upon your configuration. The majority of users
still use ``/etc/make.conf`` configuration, which has five default sets:

``system``, ``world``, ``installed``, ``version-installed``, ``vuln``

``system``, ``world``:

  These two are the same as in portage.


``version-installed``:

  ``versioned-installed`` is a set of all CPVs from the vdb. This is useful for
  ``--emptytree``.

  Example:
    If you have ``app/foo-1`` and ``bar/dar-2`` installed (and just those),
    ``versioned-installed`` would be a set containing ``-app/foo-1`` and
    ``-bar/dar-2``.


``installed``:

  ``installed`` is an unversioned set, but is slotted. Unlike
  ``version-installed``, ``installed`` can be used for "system update". Using
  ``pmerge -us installed`` over ``pmerge -u -s system -s world`` also has the
  advantage that dependency-orphaned packages are updated.

  Example:
    If you had ``app/foo-1`` slot 1, ``app/foo-2`` slot 2, ``installed`` would
    be a set containing ``app/foo:1 app/foo:2``.


``vuln``:

  Packages that are vulnerable to security bugs.

Custom Sets
-----------

Doing this for a ``make.conf`` configuration is pretty simple. Just add a file
to ``/etc/portage/sets``, containing a list of atoms. The set name is the filename.

Example: Making a kde set::

 pquery 'kde-*/*' --no-version > /etc/portage/sets/kde-set
 pmerge -uDs kde-set

Portage Equivalents
-------------------

~~~~~~~~~~~~~~~
New in pkgcore:
~~~~~~~~~~~~~~~

``--ignore-failures``:

  Ignore resolution/build failures, skipping to the next step.  Think of it as
  the equivalent of ``--skipfirst``, just without the commandline interruption.

  It goes without saying that this feature should be used with care. It is
  primarily useful for a long chain of non-critical updates, where a failure is
  not an issue.

  A good example of usage is if you want to build ``mozilla-firefox`` and
  ``openoffice`` overnight: both take a long while to build (including their
  dependencies), and the user is after getting as many packages built for the
  targets as possible, rather then having the 5th build out of 80 bail out
  without even attempting the other 75.

  Long term, this feature will likely be replaced with a more finely tuned
  option.


``--preload-vdb-state``:

  This preloads the installed packages database, causing the resolver to work
  with a complete graph, disallowing actions that conflict with installed
  packages. If it's disabled, it's possible for the requested action to
  conflict with already installed dependencies that aren't involved in the
  graph of the requested operation.

~~~~~~~~~~~~~~~~~
Moved, in pmerge:
~~~~~~~~~~~~~~~~~

``--depclean``:

  ``--clean``


``--with-bdeps``:

  ``--with-built-depends``

~~~~~~~~~~~~~~~~~~~~
Moved out of pmerge:
~~~~~~~~~~~~~~~~~~~~

``--regen``:

  See regen_

~~~~~~~~~~~~~~~
No equivalents:
~~~~~~~~~~~~~~~


``--info``:

  ``pconfig`` is the closest equivalent at the moment; it's rather verbose.

``--config``:

  This may be implemented in ``pmaint`` in the future, possibly 0.3.

``--prune``:

  Currently not implemented; Portage's implementation of it ignores slots,
  trying to force a max version for each package. This is problematic since it
  can remove needed slotted packages that are of a lesser version.

  Any package that requires slotting (automake for example) generally will
  be screwed up by ``emerge --prune``'s behaviour.

  The long term intention is to implement this functionality safely.
  Effectively, to try to minimize the resolved dependency graph to the minimal
  number of packages involved.

``--resume``, ``--skipfirst``:

  Not yet implemented.

``--metadata``:

  Not implemented: pkgcore doesn't need cache localization.

  If the user is after copying cache data around, pclone_cache can be used.

``--fetch-all-uri``:

  Not yet implemented.

``--buildpkg``:

  Not yet implemented.

``--getbinpkg``, ``--getbinpkgonly``:

  Remote Binhost v1 support will not be implemented in pkgcore, instead
  favoring the genpkgindex approach Ned Ludd (solar) has created.

  There are two main reasons for not implementing this:

  * The design of v1 allows for collisions in the package namespace; category is
    ignored. Furthermore, this collision isn't easily detectable; pulling
    ``mysql-5.0`` from the server may get you ``virtual/mysql-5.0`` or
    ``dev-db/mysql-5.0``

  * The design is god awfully slow. To get the metadata for a binpkg from an HTTP
    server, it requires (roughly) a HEAD request (tbz2 length), a ranged GET request
    to grab the last 16 bytes for the XPAK segment start, and another ranged
    request to pull the metadata.

    That's per package. You can cache, but the roundtrips add up quickly.

  The package namespace collision issue is the main reason why v1 support will
  not be added to pkgcore; v2 addresses both issues thus is the route we'll go.

``--tree``:

  This is formatter-dependent; it may be included in 0.3.

``--alphabetical``, ``--columns``:

  These won't be implemented in pkgcore.

``--changelog``:

  At some point will be accessible via ``pquery``.

Regen
-----

To regenerate run ``pregen.py <repo-name> -j <# of processors>``, which scales
around .9x linear per proc, at least through 4x for testing. This will
probably be folded into ``pmaint`` by 0.3.

Searching
=========

All searching in pkgcore is done through ``pquery``. See pquery-usage_ for how
to use ``pquery``.

Syncing
=======

``pmaint sync <reponame>`` will sync a repository. See the config document for
syncing info. If no reponame provided, it tries to sync all repositories.

Note: You should look at ``pmaint --help``, because at some point, the
'commands' for ``pmaint`` will be variable and dependent upon the repositories
available, akin to how bzr's command set changes depending on what plugins
you've enabled (commonly bzrtools).

Quickpkg
========

``pmaint copy -s vdb -t binpkg sys-apps/portage --force`` will make a binpkg
(like quickpkg).

Note: this is not a ``--buildpkg`` equivalent, as buildpkg grabs a package prior
to any preinstall mangling, so a quickpkged binpkg's contents can differ from a
binpkg built with ``--buildpkg``.

Handy backup of existing system:
``pmaint copy -s vdb -t binpkg '*' --force``

Alternatively, generating binpkgs only if they don't exist:
``pmaint copy -s vdb -t binpkg '*' --force --ignore-existing``

.. _pquery-usage: pquery-usage.rst
