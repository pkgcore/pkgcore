========
 Config
========

  **NOTE**

  If you're *truly* interested in what config does/supports currently,
  look at conf_default_types. lot of info there. This is general idea
  of it, actual code/current intentions may differ.

  ~harring

  **BACK TO YOUR PREVIOUSLY SCHEDULED PROGRAMMING**

..

  **ANOTHER NOTE**

  This is probably all not quite up-to-date after the refactoring, I
  should go through this and fix it.

  ~marienz

  **BACK TO HARRING**

win.ini style format (no you cannot burn me at the stake for this, but
you're free to try).

- sections that define type are acted upon. no type definition, and
  the section is ignored unless explicitly inherited
- if type is defined, exempting configs type, class must be defined.
- extra options are handed off to the class for initialization

repository for example::

  [rsync repo]
  type = repo
  class = pkgcore.ebuild.repository
  location = /usr/portage

Each section is capable of specifying inherit targets. Inherit's
specify the base section to pull in, and override. Depending on the
top level type, certain settings may be specified as incrementals. Use
flags fex, are incremental.

few words on each section (note the type of the section is declared
explicitly, otherwise it's just a config 'group' that is only used by
inherit's)

Sections
========

[repo]
------

- class defaults to pkgcore.ebuild.repository
- REPO_LABEL is automatically defined for all cache instances.
- frozen is a boolean, specifies if cache staleness is corrected, or
  errored out.
- can (and is advisable for rsync) specify a sync_cache.

This cache is instantiated after a sync, the normal cache's cloned
(contents) to it on sync. Repo is sync'd, it must drop its
assumptions about the current tree. In other words, you update it, it
forgets what it knows, and starts mapping things out again. Repo must
be *totally* live, no "pardon, reinstantiate it after syncing".
Shouldn't be hard via IndexableSequence; just add a method (forget?)
that wipes any internal caches to the repo. remote repo's, unless
caching, shouldn't suffer this and should just set .forget to ``lambda :
True``

[sync]
------

- can only be bound to a repo.
- must specify class

[cache]
-------

- must specify class
- REPO_LABEL is available; it's the repo 'label' (section, really)
  that the cache is associated with (repo specifies this)
- if no path is specified, assumed path is portage's base cache path,
  usually /var/cache/edb/dep
- can only be bound to a repo

[config]
--------

- if a class is specified, the class must be a callable, and will be
  handed that sections config.

the config section that defines a class is removed, and the config(s?)
returned by the callable are inserted into the global config. returned
types are marked as configs (eg, can't slip a domain in via this
route).

[domain]
--------

- config(s?) specified must be type=config
- class is optional. if it's not specified, it's assumed to be a stand
  alone domain (think root="/", normal keywords).
- if class is specified, it's passed the remaining config options,
  with the global config passed as the first arg (positional)

why allow class? cause it can be used to setup/specify interdomain
dependencies, requiring the toolchain for ppc on an x86 system for
example, or being abused for doing interdomain deps for chroot
domains.

obviously that stuff needs to be worked out, but this 'hook' should
allow it. fun fun.

[exec]
------

the fun one.

post parsing the config file that holds a type=exec section, *all*
exec sections are one by one removed and executed. valid 'commands' is
``include = some-other-file``.

don't try including a file multiple times.  cyclic detection will need
to be implemented at some point.

if class is specified for an exec type, it's the path to a callable
that returns a global level config, and the existing global level
config is updated with the returned config (iow, exec can override
what's defined in the file)

Instantiating repos/caches/syncs/etc occurs on demand, as needed, with
the exception of exec sections. In other words, the config *could*
have errors in it, but they won't be hit till the config is totally
initialized.

Secondary tool (simple bugger) that just requests all domains/repos
from the config would handle this; would force full parsing of the
config (including all package.*), and would chuck errors if
encountered. Otherwise, for sanity/speed sake, config is
executed/instantiated as needed determined by caller requests.


What does the class see for instantiation?
==========================================

dependant on the type of the section. config parser knows to remove
package.use, package.keywords, package.mask, package.unmask, and
allowed_merges, which name file(s) that are parsed, and used for a
visibility wrapper of the repo. Any slaving of repo's to a repo that
defines visibility wrappers gets the wrapped repo, not the raw repo.
All package.* are effectively location types, meaning they're
(currently) file paths, with %(CONFIG_PATH)/ assumed That assumption
may change however.

remaining options after any mangling above are handed to the class
type specified for a section. so pkgcore.ebuild.repository.__init__
will get basedir="/usr/portage" for a dict arg. (Example above)


allowed_merges file
-------------------

Specifies atoms that control what can be merged. Think of it as either
the uber "you ain't merging this bubba" for vdb (not very useful), or,
bit more useful, list of atoms that are binpkg'd, specifiable per
merge_target repo. can't apply it to an ebuild repo, can apply it to a
binpkg/rpm repo though.


package.*, visibility wrappers
------------------------------

A repo class *also* can, and likely will define it's own visibility
wrappers, as will the config (ACCEPT_KEYWORDS). Minor design note;
wrappers take away from repo.match's capabilities to hand off crap to
a potentially faster resolver remotely (consider situation where the
repo is a rdbms; visibility filter can be handed off to pl/sql funcs
or massive where clause)

The way this is implemented is that package.* are translated into
restrictions, which are then slipped into a 
``pkgcore.repository.visibility.tree`` instance that wraps the raw repo.


profiles
--------

Profiles can be implemented as config sub groups (think inherit on steroids); 
that said, they're not implemented that way currently, they're implemented as
stand alone objects.

if profile is specified, creates repo visibility wrappers to work with
it. implicit implication is that you can specify a profile per actual
repository. not sure about this. can also specify it per config, and
per domain.

profile is specified per config. all sections can specify an 'inherit'
target(s), which is a section to pull values from, and override.


MAKE.CONF BACKWARDS COMPATIBILITY
=================================

**note**
this isn't yet implemented, as such, subject to change.


assumes /etc/make.profile points at a valid profile , which is used to define
the profile for the config.  make.conf is read, and converted into a config 
section, all of this is bound under a default domain with root="/".
PORTDIR is removed and used for ebuild repo's location PORTDIR_OVERLAY is 
removed, and sections are created for each, slaving them to PORTDIR, creating 
a final repositorySet that binds them together.
/etc/portage/package.* is used as a visibility wrapper on repositorySet.

if FEATURES="binpkg" is defined, then a binpkg repository section is 
generated, and PKGDIR is removed and used as location for the repository.

defaults are lifted from /usr/share/portage/defaults.config ; basically 
make.global, but in the new config format, and treated as a non-modifiable 
data file, and stored elsewhere

Note that effectively make.conf's existance just serves to mangle 
defaults.config.  it's a mapping of old options into new, with all unknown 
options being used as config fodder (literally, default config section gets 
'em).

