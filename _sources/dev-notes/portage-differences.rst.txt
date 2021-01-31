===========================
Pkgcore/Portage differences
===========================

Disclaimer
----------

Pkgcore moves fairly fast in terms of development- we will strive to keep this doc
up to date, but it may lag behind the actual code.

--------------------------
Ebuild environment changes
--------------------------

All changes are either glep33 related, or a tightening of the restrictions on
the env to block common snafus that localize the ebuilds environment to that
machine.

- portageq based functions are disabled in the global scope.  Reasoning for this
  is that of QA- has_version/best_version **must not** affect the generated
  metadata.  As such, portageq calls in the global scope are disabled.

- inherit is disabled in all phases but depend and setup.  Folks no longer do
  it, but inherit from within one of the build/install phases is now actively
  blocked.

- The ebuild env is now *effectively* akin to suspending the process, and restarting
  it.  Essentially, transitioning between ebuild phases, the ebuild environment
  is snapshotted, cleaned of irrevelent data (bash forced vars for example, or
  vars that pkgcore sets for the local system on each shift into a phase), and
  saved. Portage does this partially (re-execs ebuilds/eclasses, thus stomping
  the env on each phase change), pkgcore does it fully. As such, pkgcore is
  capable of glep33, while portage is not (env fixes are the basis of glep33).

- ebuild.sh has been daemonized (ebd). The upshot of this is that regen is
  roughly 2x faster (careful reuse of ebd instances rather then forcing bash to
  spawn all over).  Additional upshot of this is that their are bidirectional
  communication pipes between ebd and the python parent- env inspection,
  logging, passing requests up to the python side (has_version/best_version for
  example) are now handled within the existing processes.  Design of it from
  the python side is that of an extensible event handler, as such it's
  extremely easy to add new commands in, or special case certain things.

- The ebd now protects itself from basic fiddling. Ebuild generated state
  **must** work as long as the EAPI is the same, regardless of the generating
  portage version, and the portage version that later uses the saved state
  (simple example, generated with portage-2.51, if portage 3 is EAPI compliant
  with that env, it must not allow it's internal bash changes to break the env).
  As such, certain funcs are not modifiable by the ebuild- namely, internal
  portage/pkgcore functionality, hasq/useq for example. Those functions that
  are read-only also are not saved in the ebuild env (they should be supplied
  by the portage/pkgcore instance reloading the env).

-----------------------
Repository Enhancements
-----------------------

Pkgcore internally uses a sane/uniform repository abstraction- the benefits
of this are:

- repository class (which implements the accessing of the on disk/remote tree)
  is pluggable.  Remote source or installed repos are doable, as is having your
  repository tree ran strictly from downloaded metadata (for example), or
  running from a tree stored in a tarball/zip file (mildly crazy, but it's
  doable).

- separated repository instances.  We've not thrown out overlays (as paludis
  did), but pkgcore doesn't force every new repository to be an overlay of the
  default 'master' repo as portage does.

- optimized repository classes- for the usual vdb and ebuild repository
  (those being on disk backwards compatible with portage 2.x), the number of
  syscalls required was drastically reduced, with ondisk info (what packages
  available per category for example) cached.  It is a space vs time trade
  off, but the space trade off is neglible (couple of dict with worst case,
  66k mappings)- as is, portage's listdir caching consumed a bit more memory
  and was slower, so all in all a gain (mainly it's faster with using
  slightly less memory then portages caching).

- unique package instances yielded from repository.  Pkgcore uses a package
  abstraction internally for accessing metadata/version/category, etc- all
  instances returned from repositories are unique immutable instances.
  Gain of it is that if you've got dev-util/diffball-0.7.1 sitting in memory
  already, it will return that instance instead of generating a new one- and
  since metadata is accessed via the instance, you get at most **one** load
  from the cache backend per instance in memory- cache pull only occurs when
  required also.  As such, far faster for when doing random package accessing
  and storing of said packages (think repoman, dependency resolution, etc).
