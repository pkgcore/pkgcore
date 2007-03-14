===============
Getting Started
===============

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

  **Warning:** This can break your system if
  incorrectly used. Check with --pretend before running it.

  Additionally, it currently defaults to identifying only whats
  required for world/system; installed packages don't require their build
  depends to be satisfied, as such --clean will identify them for removal if
  they're not runtime depended upon.

  If you want --clean to preserve your build depends, use the -B option.


Sets
----

Available sets are dependant upon your configuration- majority of users still
use make.conf configuration, which has five default sets:

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

  ignore resolution/build failures, skipping to the next step.  Think of it
  as the equiv of --skipfirst, just without the commandline interuption.

  Goes without saying, this feature should be used with care- primarily useful
  for a long chain of non critical updates, where a failure is a non issue.

  Good example of usage is if you want to build mozilla-firefox and openoffice
  during the night- both take a long while to build (including their deps), and
  the user is after getting as many packages built for the targets as possible,
  rather then having the 5th build out of 80 bail out even attempting the other
  75.

  Long term, this feature will likely be replaced with a more fine tuned option.


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

  pconfig is the closest equivalent at the moment- rather verbose.

--config:

  This may be implemented in pmaint in the future, possible 0.3.

--prune:

  Currently not implemented; portages implementation of it ignores slots,
  trying to force a max version for each package- this is problematic however
  since it can remove needed slotted packages that are of a lesser version.

  Any package that requires slotting (automake for example) generally will
  be screwed up by emerge --prunes behaviour.

  Long term intention is to implement this functionality safely- effectively
  try to minimize the resolved dependency graph to minimal number of packages
  involved.

--resume:

--skipfirst:

  Not yet implemented.

--metadata:

  Not implemented- pkgcore doesn't need cache localization.

  If the user is after copying cache data around, pclone_cache can be used.

--fetch-all-uri:

  Not yet implemented.

--buildpkg:

  Not yet implemented.

--getbinpkg:

--getbinpkgonly:

  Remote Binhost v1 support will not be implemented in pkgcore, instead
  favoring the genpkgindex approach Ned Ludd (solar) has created.

  Reasoning for this comes down to two main reasons-

  * design of v1 allows for collisions in the package namespace, category 
    is ignored.  Further, this collision isn't easily detectable- pulling
    mysql-5.0 from the server may get you virtual/mysql-5.0 or dev-db/mysql-5.0

  * design is god awfully slow.  To get the metadata for a binpkg from an HTTP
    server, requires (roughly) a HEAD request (tbz2 length), ranged GET request
    to grab the last 16 bytes for the XPAK segment start, another ranged
    request to pull the metadata.

    That's per package.  Can cache, but the roundtrips add up quickly.

  The package namespace collision issue is the main reason why v1 support will
  not be added to pkgcore; v2 addresses both issues thus is the route we'll go.

--tree:

  This is formatter dependant, it may be included in 0.3.

--alphabetical:

--columns:

  These won't be implemented in pkgcore.

--changelog:

  At some point will be accessible via pquery.

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
info.  No reponame provided, tries to sync all repositories.

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

Handy backup of existing system-
``pmaint copy -s vdb -t binpkg '*' --force``

Alternatively, generating binpkgs only if they don't exist-
``pmaint copy -s vdb -t binpkg '*' --force --ignore-existing``

.. _pquery-usage: pquery-usage.rst
