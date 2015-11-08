=======
WARNING
=======

This is the original brain dump from harring; it *is* not guaranteed to
be accurate to the current design, it's kept around to give an idea
of where things came from to contrast to what is in place now.


==============
 Introduction
==============

e'yo. General description of layout/goals/info/etc, and semi sortta api.

That and aggregator of random ass crazy quotes should people get bored.

**DISCLAIMER**

This ain't the code.

In other words, the actual design/code may be radically different, and
this document probably will trail any major overhauls of the
design/code (speaking from past experience).

Updates welcome, as are suggestions and questions- please dig through
all documentations in the dir this doc is in however, since there is a
lot of info (both current and historical) related to it. Collapsing
info into this doc is attempted, but explanation of the full
restriction protocol (fex) is a *lot* of info, and original idea is
from previous redesign err... designs. Short version, historical, but
still relevant info for restriction is in layout.txt. Other
subsystems/design choices have their basis quite likely from other
docs in this directory, so do your homework please :)

Terminology
===========

cp
  category/package

cpv
  category/package-version

ROOT
  livefs merge point, fex /home/bharring/embedded/arm-target or
  more commonly, root=/

vdb
  /var/db/pkg, installed packages database.

domain
  combination of repositories, root, and build information (use
  flags, cflags, etc).  config data + repositories effectively.

repository
  trees.  ebuild tree, binpkg tree, vdb tree, etc.

protocol
  python name for design/api.  iter() fex, is a protocol; for iter(o)
  it does i=o.__iter__(); the returned object is expected to yield an
  element when i.next() is called, till it runs out of elements (then
  throwing a StopIteration).
  hesitate to call it defined hook on a class/instance, but this
  (crappy) description should suffice.

seq
  sequence, lists/tuples

set
  list without order (think dict.keys())

General design/idea/approach/requirements
=========================================

All pythonic components installed by pkgcore *must* be within
pkgcore.* namespace. No more polluting python's namespace, plain and
simple. Third party plugins to pkgcore aren't bound by this however
(their mess, not ours).

API flows from the config definitions, *everything* internal is
effectively the same. Basically, config data gives you your starter
objects which from there, you dig deeper into the innards as needed
action wise.

The general design is intended to heavily abuse OOP.
Further, delegation of actions down to components *must* be abided by,
example being repo + cache interaction. repo does what it can, but for
searching the cache, let the cache do it. Assume what you're
delegating to knows the best way to handle the request, and probably
can do its job better then some external caller (essentially).

Actual configuration is pretty heavily redesigned. Classes and
functions that should be constructed based on data from the user's
configuration have a "hint" describing their arguments. The global
config class uses these hints to convert and typecheck the values in
the user's configuration. Actual configuration file reading and type
conversion is done by a separate class, meaning the global manager is
not tied to a single format, or even to configuration read from a file
on disk.

Encapsulation, extensibility/modularity, delegation, and allowing
parallelizing of development should be key focuses in
implementing/refining this high level design doc. Realize
parallelizing is a funky statement, but it's apt; work on the repo
implementations can proceed without being held up by cache work, and
vice versa.

Final comment re: design goals, defining chunks of callable code and
plugging it into the framework is another bit of a goal. Think
twisted, just not quite as prevalent (their needs/focus is much
different from ours, twisted is the app, your code is the lib, vice
versa for pkgcore).

Back to config. Here's general notion of config 'chunks' of the
subsystem, (these map out to run time objects unless otherwise stated)::

  domain
  +-- profile (optional)
  +-- fetcher (default)
  +-- repositories
  +-- resolver (default)
  +-- build env data?
  |    never actually instantiated, no object)
  \-- livefs_repo (merge target, non optional)

  repository
  +-- cache   (optional)
  +-- fetcher (optional)
  +-- sync    (optional, may change)
  \-- sync cache (optional, may chance)

  profile
  +-- build env?
  +-- sets (system mainly).
  \-- visibility wrappers

domain is configuration data, accept_(license|keywords), use, cflags,
chost, features, etc. profile, dependent on the profile class you
choose is either bound to a repository, or to user defined location on
disk (/etc/portage/profile fex). Domain knows to do incremental crap
upon profile settings, lifting package.* crap for visibility wrappers
for repositories also.

repositories is pretty straightforward.  portdir, binpkg, vdb, etc.

Back to domain. Domain's are your definition of pretty much what can
be done. Can't do jack without a domain, period. Can have multiple
domains also, and domains do *not* have to be local (remote domains
being a different class type). Clarifying, think of 500 desktop boxes,
and a master box that's responsible for managing them. Define an
appropriate domain class, and appropriate repository classes, and have
a config that holds the 500 domains (representing each box), and you
can push updates out via standard api trickery. In other words, the
magic is hidden away, just define remote classes that match defined
class rules (preferably inheriting from the base class, since
isinstance sanity checks will become the norm), and you could do
emerge --domain some-remote-domain -u glsa on the master box. Emerge
won't know it's doing remote crap. Pkgcore won't even. It'll just load
what you define in the config.

Ambitious? Yeah, a bit. Thing to note, the remote class additions will
exist outside of pkgcore proper most likely. Develop the code needed
in parallel to fleshing pkgcore proper out.

Meanwhile, the remote bit + multiple domains + class overrides in
config definition is _explicitly_ for the reasons above. That and
x-compile/embedded target building, which is a bit funkier.

Currently, portage has DEPEND and RDEPEND. How do you know what needs
be native to that box to build the package, what must be chost atoms?
Literally, how do you know which atoms, say the toolchain, must be
native vs what package's headers/libs must exist to build it? We need
an additional metadata key, BDEPEND (build depends).

If you have BDEPEND, you know what actually is ran locally in building
a package, vs what headers/libs are required. Subtle difference, but
BDEPEND would allow (with a sophisticated depresolver) toolchain to be
represented in deps, rather then the current unstated dep approach
profiles allow.

Aside from that, BDEPEND could be used for x-compile via inter-domain
deps; a ppc target domain on a x86 box would require BDEPEND from the
default domain (x86). So... that's useful.

So far, no one has shot this down, moreso, come up with reasons as to
why it wouldn't work, the consensus thus far is mainly "err, don't
want to add the deps, too much work". Regarding work, use indirection.

virtual/toolchain-c
  metapkg (glep37) that expands out (dependent on arch) into whatever
  is required to do building of c sources
virtual/toolchain-c++
  same thing, just c++
virtual/autootols
  take a guess.
virtual/libc
  this should be tagged into rdepends where applicable, packages that
  directly require it (compiled crap mainly)

Yes it's extra work, but the metapkgs above should cover a large chunk
of the tree, say >90%.

Config design
=============

Portage thus far (<=2.0.51*) has had variable ROOT (livefs merge
point), but no way to vary configuration data aside from via a
buttload of env vars. Further, there has been only one repository
allowed (overlays are just that, extensions of the 'master'
repository). Addition of support of any new format is mildly insane
due to hardcoding up the wing wang in the code, and
extension/modification of existing formats (ebuild) has some issues
(namely the doebuild block of code).

Goal is to address all of this crap. Format agnosticism at the
repository level is via an abstracted repository design that should
supply generic inspection attributes to match other formats.
Specialized searching is possible via match, thus extending the
extensibility of the prototype repository design.

Format agnosticism for building/merging is somewhat reliant on the
repo, namely package abstraction, and abstraction of building/merging
operations.

On disk configurations for alternatives formats is extensible via
changing section types, and plugging them into the domain definition.

Note alt. formats quite likely will never be implemented in pkgcore
proper, that's kind of the domain of pkgcore addons. In other words,
dpkg/rpm/whatever quite likely won't be worked on by pkgcore
developers, at least not in the near future (too many other things to
do).

The intention is to generalize the framework so it's possible for
others to do so if they choose however.

Why is this good? Ebuild format has issues, as does our profile
implementation. At some point, alternative formats/non-backwards
compatible tweaks to the formats (ebuild or profile) will occur, and
then people will be quite happy that the framework is generalized
(seriously, nothing is lost from a proper abstracted design, and
flexibility/power is gained).


config's actions/operation
==========================

pkgcore.config.load_config() is the entrance point, returns to you a
config object (pkgcore.config.central). This object gives you access
to the user defined configs, although only interest/poking at it
should be to get a domain object from it.

domain object is instantiated by config object via user defined
configuration. domains hold instantiated repositories, bind profile +
user prefs (use/accept_keywords) together, and _should_ simplify this
data into somewhat user friendly methods. (define this better).

Normal/default domain doesn't know about other domains, nor give a
damn. Embedded targets are domains, and _will_ need to know about the
livefs domain (root=/), so buildplan creation/handling may need to be
bound into domains.


Objects/subsystems/stuff
========================

So... this is general naming of pretty much top level view of things,
stuff emerge would be interested in (and would fool with). hesitate to
call it a general api, but it probably will be as such, exempting any
abstraction layer/api over all of this (good luck on that one }:] ).


IndexableSequence
-----------------

functions as a set and dict, with caching and on the fly querying of
info. mentioned due to use in repository and other places... (it's a
useful lil sucker)

This actually is misnamed. the order of iteration isn't necessarily
reproducable, although it's usually constant. IOW, it's normally a
sequence, but the class doesn't implicitly force it


LazyValDict
-----------

similar to ixseq, late loading of keys, on fly pulling of values as
requested.

global config object (from pkgcore.config.load_config())
--------------------------------------------------------

see config.rst.

domain object
-------------

bit of debate on this one I expect. any package.{mask,unmask,keywords}
mangling is instantiated as a wrapper around repository instances upon
domain instantiation. code *should* be smart and lift any
package.{mask,unmask,keywords} wrappers from repositoriy instances and
collapse it, pointing at the raw repo (basically don't have N
wrappers, collapse it into a single wrapper). Not worth implementing
until the wrapper is a faster implementation then the current
pkgcore.repository.visibility hack though (currently O(N) for each pkg
instance, N being visibility restrictions/atoms). Once it's O(1),
collapsing makes a bit more sense (can be done in parallel however).

a word on inter repository dependencies... simply put, if the
repository only allows satisfying deps from the same repository, the
package instance's \*DEPEND atom conversions should include that
restriction. Same trickery for keeping ebuilds from depping on
rpm/dpkg (and vice versa).

.repositories
  in the air somewhat on this one. either indexablesequence, or a
  repositorySet. Nice aspect of the latter is you can just use .match
  with appropriate restrictions. very simply interface imo, although
  should provide a way to pull individual repositories/labels of said
  repos from the set though. basically, mangle a .raw_repo
  indexablesequence type trick (hackish, but nail it down when reach
  that bridge)


build plan creation
-------------------

<TODO insert details as they're fleshed out>

sets
----

TODO chuck in some details here. probably defined via user config
and/or profile, although what's it define? atoms/restrictions?
itermatch might be useful for a true set.


build/setup operation
---------------------

(need a good name for this; dpkg/rpm/binpkg/ebuild's 'prepping' for
livefs merge should all fall under this, with varying use of the
hooks)

.build()
  do everything, calling all steps as needed
.setup()
  whatever tmp dirs required, create 'em.
.req_files()
  (fetchables, although not necessarily with url (restrict="fetch"...)
.unpack()
  guess.
.configure()
  unused till ebuild format version two (ya know, that overhaul we've
  been kicking around? :)
.compile()
  guess.
.test()
  guess.
.install()
  install to tmp location.  may not be used dependent on the format.
.finalize()
  good to go.  generate (jit?) contents/metadata attributes, or
  returns a finalized instance should generate a immutable package instance.

repo change operation
---------------------

base class.

.package
  package instance of what the action is centering around.
.start()
  notify repo we're starting (locking mainly, although prerm/preinst
  hook also)
.finish()
  notify repo we're done.
.run()
  high level, calls whatever funcs needed.  individual methods are
  mainly for ui, this is if you don't display "doing install now...
  done... doing remove now... done" stuff.


remove operation
----------------

derivative of repo change operation.

.remove()
  guess.
.package
  package instance of what's being yanked.

install operation
-----------------

derivative of repo change operation

.package
  what's being installed.
.install()
  install it baby.

merge operation
---------------

derivative of repo remove and install (so it has .remove and .install,
which must be called in .install and .remove order)

.replacing
  package instance of what's being replaced.
.package
  what's being installed

fetchables
----------

basically a dict of stuff jammed together, just via attribute access
(think c struct equiv)

.filename
  ..
.url
  tuple/list of url's.
.chksums
  dict of chksum:val


fetcher
-------

hey hey.  take a guess.

worth noting, if fetchable lacks ``.chksums["size"]``, it'll wipe any
existing file. if size exists, and existing file is bigger, wipe file,
and start anew, otherwise resume. mirror expansion occurs here, also.

.fetch(fetchable, verifier=None) # if verifier handed in, does
verification.

verifier
--------

note this is basically lifted conceptually from mirror_dist. if
wondering about the need/use of it, look at that source.

verify()
  handed a fetchable, either False or True


repository
----------

this should be format agnostic, and hide any remote bits of it. this
is general info for using it, not designing a repository class

.mergable()
  true/false.  pass a pkg to it, and it reports whether it can merge
  that or not.
.livefs
  boolean, indicative of whether or not it's a livefs target- this is
  useful for resolver, shop it to other repos, binpkg fex prior to
  shopping it to the vdb for merging to the fs.  Or merge to livefs,
  then binpkg it while continuing further building dependent on that
  package (ui app's choice really).
.raw_repo
  either it weakref's self, or non-weakref refs another repo. why is
  this useful? visibility wrappers... this gives ya a way to see if
  p.mask is blocking usable packages fex. useful for the UI, not too
  much for pkgcore innards.
.frozen
  boolean.  basically, does it account for things changing without
  its knowledge, or does it not.  frozen=True is faster for ebuild
  trees for example, single check for cache staleness. frozen=False
  is slower, and is what portage does now (meaning every lookup of a
  package, and instantiation of a package instance requires mtime
  checks for staleness).
.categories
  IndexableSequence, if iterated over, gives ya all categories, if
  getitem lookup, sub-category category lookups. think
  media/video/mplayer
.packages
  IndexableSequence, if iterated over, all package names.  if getitem
  (with category as key), packages of that category.
.versions
  IndexableSequence, if iterated over, all cpvs.  if getitem (with
  cat/pkg as key), versions for that cp
.itermatch()
  iterable, given an atom/restriction, yields matching package
  instances.
.match()
  ``def match(self, atom): return list(self.itermatch(atom))``
  voila.
.__iter__()
  in other words, repository is iterable.  yields package instances.
.sync()
  sync, if the repo swings that way. flesh it out a bit, possibly
  handing in/back ui object for getting updates...

digressing for a moment...

note you can group repositories together, think portdir +
portdir_overlay1 + portdir_overlay2. Creation of a repositoryset
basically would involve passing multiple instantiating repo's, and
depending on that classes semantics, it internally handles the
stacking (right most positional arg repo overrides 2nd right most, ...
overriding left most) So... stating it again/clearly if it ain't
obvious, everything is configuration/instantiating of objects, chucked
around/mangled by the pkgcore framework.

What *isn't* obvious is that since a repository set gets handed
instantiated repositories, each repo, *including* the set instance,
can should be able to have its own cache (this is assuming it's
ebuild repos through and through). Why? Cache data doesn't change for
the most part exempting which repo a cpv is from, and the eclass
stacking. Handled individually, a cache bound to portdir *should* be
valid for portdir alone, it shouldn't carry data that is a result of
eclass stacking from another overlay + that portdir. That's the
business of the repositoryset. Consequence of this is that the
repositoryset needs to basically reach down into the repository it's
wrapping, get the pkg data, *then* rerequest the keys from that ebuild
with a different eclass stack. This would be a bit expensive, although
once inherit is converted to a pythonic implementation (basically
handing the path to the requested eclass down the pipes to
ebuild*.sh), it should be possible to trigger a fork in the inherit,
and note python side that multiple sets of metadata are going to be
coming down the pipe. That should alleviate the cost a bit, but it
also makes multiple levels of cache reflecting each repository
instance a bit nastier to pull off till it's implemented.

So... short version. Harring is a perfectionist, and says it should be
this way. reality of the situation makes it a bit trickier. Anyone
interested in attempting the mod, feel free, otherwise harring will
take a crack at it since he's being anal about having it work in such
a fashion.

Or... could do thus. repo + cache as a layer, wrapped with a 'regen'
layer that handles cache regeneration as required. Via that, would
give the repositoryset a way to override and use its own specialized
class that ensures each repo gets what's proper for its layer. Think
raw_repo type trick.

continuing on...


cache
-----

ebuild centric, although who knows (binpkg cache ain't insane ya
know). short version, it's functionally a dict, with sequence
properties (iterating over all keys).

.keys()
  return every cpv/package in the db.
.readonly
  boolean. Is it modifiable?
.match()
  Flesh this out. Either handed a metadata restriction (or set of
  'em), or handed dict with equiv info (like the former). ebuild
  caches most likely *should* return mtime information alongside,
  although maybe dependent on readonly. purpose of this? Gives you a
  way to hand off metadata searching to the cache db, rather then the
  repo having to resort to pulling each cpv from the cache and doing
  the check itself. This is what will make rdbms cache backends
  finally stop sucking and seriously rocking, properly implemented at
  least. :) clarification, you don't call this directly, repo.match
  delegates off to this for metadata only restrictions


package
-------

this is a wrapped, *constant* package. configured ebuild src, binpkg,
vdb pkg, etc. ebuild repositories don't exactly and return this- they
return unconfigured pkgs, which I'm not going to go into right now
(domains only see this protocol, visibility wrappers see different)

.depends
  usual meaning.  ctarget depends
.rdepends
  usual meaning.  ctarget run time depends. seq,
.bdepends
  see ml discussion. chost depends, what's executed in building this
  (toolchain fex). seq.
.files
  get a better name for this. doesn't encompas ``files/*``, but could be
  slipped in that way for remote. encompasses restrict fetch (files
  with urls), and chksum data. seq.
.description
  usual meaning, although remember probably need a way to merge
  metadata.xml lond desc into the more mundane description key.
.license
  usual meaning, depset
.homepage
  usual. Needed?
.setup()
  Name sucks. gets ya the setup operation, which does building/whatever.
.data
  Raw data.  may not exist, don't screw with it unless you know what
  it is, and know the instance's .data layout.
.build()
  if this package is buildable, return a build operation, else return None

restriction
-----------

see layout.txt for more fleshed out examples of the idea. note, match
and pmatch have been reversed namewise.

.match()
  handed package instance, will return bool of whether or not this
  restriction matches.
.cmatch()
  try to force the changes; this is dependent on the package being
  configurable.
.itermatch()
  new one, debatable. short version, giving a sequence of package
  instances, yields true/false for them. why might this be desirable?
  if setup of matching is expensive, this gives you a way to amoritize
  the cost. might have use for glsa set target. define a restriction
  that limits to installed pkgs, yay/nay if update is avail...

restrictionSet
--------------

mentioning it merely cause it's a grouping (boolean and/or) of
individual restrictions an atom, which is in reality a category
restriction, package restriction, and/or version restriction is a
boolean and set of restrictions

ContentsRestriction
-------------------

whats this you say? a restriction for searching the vdb's contents db?
Perish the thought! ;)

metadataRestriction
-------------------

Mentioning this for the sake of pointing out a subclass of it,
DescriptionRestriction- this will be a class representing matching
against description data. See repo.match and cache.match above. The
short version is that it encapsulates the description search (a *very*
slow search right now) so that repo.match can hand off to the cache
(delegation), and the cache can do the search itself, however it sees
fit.

So... for the default cache, flat_list (19500 ebuilds == 19500 files to
read for a full searchDesc), still is slow unless flat_list gets some
desc. cache added to it internally. If it's a sql based cache, the
sql_template should translate the query into the appropriate select
statement, which should make it *much* faster.

Restating that, delegation is *absolutely* required. There have been
requests to add intermediate caches to the tree, or move data (whether
collapsing metadata.xml or moving data out of ebuilds) so that the
form it is stored is in quicker to search. These approaches are wrong.
Should be clear from above that a repository can, and likely will be
remote on some boxes. Such a shift of metadata does nothing but make
repository implementations that harder, and shift power away from what
knows best how to use it. Delegation is a massively more powerful
approach, allowing for more extensibility, flexibility and *speed*.

Final restating- searchDesc is matching against cache data. The cache
(whether flat_list, anydbm, sqlite, or a remote sql based cache) is
the *authority* about the fastest way to do searches of its data.
Programmers get pist off when users try and tell them how something
internally should be implemented- it's fundamentally the same
scenario. The cache class the user chooses knows how to do its job
the best, provide methods of handing control down to it, and let it do
its job (delegation). Otherwise you've got a backseat driver
situation, which doesn't let those in the know, do the deciding (cache
knows, repo doesn't).

Mind you not trying to be harsh here. If in reading through the full
doc you disagree, question it; if after speeding up current cache
implementation, note that any such change must be backwards
compatible, and not screw up the possibilities of
encapsulation/delegation this design aims for.

logging
-------

flesh this out (define this basically). short version, no more
writemsg type trickery, use a proper logging framework.

ebuild-daemon.sh
----------------

Hardcoded paths *have* to go. /usr/lib/portage/bin == kill it. Upon
initial loadup of ebuild.sh, dump the default/base path down to the
daemon, *including* a setting for /usr/lib/portage/bin . Likely
declare -xr it, then load the actual ebuild*.sh libs. Backwards
compatibility for that is thus, ebuild.sh defines the var itself in
global scope if it's undefined. Semblence of backwards compatibility
(which is actually somewhat pointless since I'm about to blow it out
of the water).

Ebuild-daemon.sh needs a function for dumping a _large_ amount of data
into bash, more then just a line or two.

For the ultra paranoid, we load up eclasses, ebuilds, profile.bashrc's
into python side, pipe that to gpg for verification, then pipe that
data straight into bash. No race condition possible for files
used/transferred in this manner.

A thought. The screw around speed up hack preload_eclasses added in
ebd's heyday of making it as fast as possible would be one route;
Basically, after verification of an elib/eclass, preload the eclass
into a func in the bash env. and declare -r the func after the fork.
This protects the func from being screwed with, and gives a way to (at
least per ebd instance) cache the verified bash code in memory.

It could work surprisingly enough (the preload_eclass command already
works), and probably be fairly fast versus the alternative. So... the
race condition probably can be flat out killed off without massive
issues. Still leaves a race for perms on any ``files/*``, but neh. A)
That stuff shouldn't be executed, B) security is good, but we can't
cover every possibility (we can try, but dimishing returns)

A lesser, but still tough version of this is to use the indirection
for actual sourcing to get paths instead. No EBUILD_PATH, query python
side for the path, which returns either '' (which ebd interprets as
"err, something is whacked, time to scream"), or the actual path.

In terms of timing, gpg verification of ebuilds probably should occur
prior to even spawning ebd.sh. profile, eclass, and elib sourcing
should use this technique to do on the fly verification though. Object
interaction for that one is going to be *really* fun, as will be
mapping config settings to instantiation of objs.
