Portage Differences
+++++++++++++++++++

Currently portage handles all actions primarily through one script; emerge.
pkgcore breaks this functionality down into 3 scripts: pmerge, pmaint, and
pquery.

Pmerge
======

pmerge is fairly similar to emerge in most usage instances:

Basic Usage
-----------

``pmerge -us world``
  Update world
``pmerge -uDs world``
  Update world deeply - the resolver will check the
  dependencies of each package's dependencies.
``pmerge -p dev-util/bzrtools``
  Pretend to install bzrtools
``pmerge -C \<sys-kernel/gentoo-sources-2.6.19``
  Remove gentoo-sources less than 2.6.19
``pmerge --clean``
  Remove unused packages.

  **Warning:** This can break your system if
  incorrectly used. Check with --pretend before running it. 

Sets
----

There are five default sets:
system, world, installed, version-installed, vuln

system:

world:

  These two are the same as in portage.


version-installed:

  versioned-installed is a set of all cpv's from the vdb. This is useful for
  --emptytree.

  Example:
    If you have app/foo-1 and bar/dar-2 installed (and just those),
    versioned-installed would be a set containing -app/foo-1 and -bar/dar-2.


installed:

  installed is an unversioned set, but is slotted. Unlike version-installed,
  installed can be used for "system update". Using ``pmerge -us installed``
  over ``pmerge -u -s system -s`` world also has the advantage that
  dependency-orphaned packages are updated.

  Example:
    If you had app/foo-1 slot 1, app/foo-2 slot 2, installed would be a set
    containing would be app/foo:1 app/foo:2.


vuln:

  Packages that are vulnerable to security bugs.

Custom Sets
-----------

Doing this for a make.conf configuration is pretty simple. Just add a file
to /etc/portage/sets, containing a list of atoms. The set name is the filename.

Example: Making a kde set:
  ``pquery 'kde-*/*' --no-version > /etc/portage/sets/kde-set``
  ``pmerge -uDs kde-set``

Portage Equivalents
-------------------

~~~~~~~~~~~~~~~
New in pkgcore:
~~~~~~~~~~~~~~~

--ignore-failures:

  ignore resolution failures


--preload-vdb-state:

  This preloads the installed packages database causing the resolver to work
  with a complete graph, disallowing actions that confict with installed
  packages. If it's disabled, it's possible for the requested action to
  conflict with already installed dependencies that aren't involved in the
  graph of the requested operation.

~~~~~~~~~~~~~~~~~
Moved, in pmerge:
~~~~~~~~~~~~~~~~~

--depclean:

  --clean


--with-bdeps:

  --with-built-depends

~~~~~~~~~~~~~~~~~~~~
Moved out of pmerge:
~~~~~~~~~~~~~~~~~~~~

--regen:

  See regen_

~~~~~~~~~~~~~~~
No equivalents:
~~~~~~~~~~~~~~~


--info:

  pconfig is the closest equivalent.

--config:

  This may be implemented in pmaint in the future, possible 0.3.

--clean:

--prune:

  These aren't yet implemented, use pmerge --clean to get a depclean
  equivalent.

--resume:

--skipfirst:

  Not yet implemented.

--metadata:

  Not implemented - we don't do cache transferance as we don't need it.


--fetch-all-uri:

  Not yet implemented.

--buildpkg:

  Not yet implemented.

--getbinpkg:

--getbinpkgonly:

  This is binhost version 1 specific, which won't be implemented in pkgcore.

--tree:

  This is formatter dependant, it may be included in 0.3.

--alphabetical:

--changelog:

--columns:

  These won't be implemented in pkgcore.

Regen
-----

To regenerate run ``pregen.py <repo-name> -j <# of processors>``, which scales
around .9x linear per proc, at least through 4x for testing. This will
probably be folded into pmaint by 0.3.

Searching
=========

All search in pkgcore is done through pquery. See
pquery-usage_ for how to use pquery.

Syncing
=======

``pmaint sync <reponame>`` will sync a repository. See config doc for syncing
info.

Note: You should look at pmaint --help, because at some point, the 'commands'
for pmaint will be variable and dependant upon the repositories available, 
akin to how bzr's command set changes dependant on what plugins you've enabled
(commonly bzrtools).

Quickpkg
========

``pmaint copy -s vdb -t binpkg sys-apps/portage --force`` will make a binpkg
(like quickpkg).

Note: this is not a --buildpkg equiv, as buildpkg grabs a package prior to
any preinst mangling, so a quickpkg'ed binpkg's contents can differ from a
binpkg built with --buildpkg.

.. _pquery-usage: pquery-usage.rst
