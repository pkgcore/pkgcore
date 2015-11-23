===============================
 Feature (FEATURES) categories
===============================

relevant list of features
=========================

* autoaddcvs
* buildpkg
* ccache
* collision-protect
* confcache
* cvs
* digest
* distcc
* distlocks
* fixpackages
* getbinpkg
* gpg
* keeptemp
* keepwork
* mirror
* noclean (keeptemp, keepwork)
* nodoc
* noinfo
* noman
* nostrip
* notitles
* sandbox
* severe
* severer (dumb spanky)
* sfperms
* sign
* strict
* suidctl
* test
* userpriv
* usersandbox

Undefined
---------

fixpackages

Dead
----

* usersandbox
* noclean
* getbinpkg (it's a repo type, not a global feature)
* buildpkg  (again, repo thing.  moreso ui/buildplan execution)

Build
-----

* keeptemp, keepwork, noclean, ccache, distcc
* sandbox, userpriv
* confcache
* noauto (fun one)
* test

repos or wrappers
-----------------

Mutables
~~~~~~~~

* autoaddcvs
* cvs
* digest
* gpg
* no{doc,info,man,strip}
* sign
* sfperms
* collision-protect (vdb only)

Immutables
~~~~~~~~~~

* strict
* severe ; these two are repository opts on gpg repo class

Fetchers
~~~~~~~~

* distlocks, sort of.
