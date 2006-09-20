==========
Rough TODO
==========

- sandbox and fakeroot don't work right now (doesn't properly disable)

- sync subsystem. ***
  Threw out the old refactoring, too portage specific; exists in 
  sandbox/dead_code , design sucked also.

- observer objects for reporting back events from merging/unmerging
  cpython 'tee' is needed, contact harring for details.
  elog is bound to this also

- Possibly convert to cpython:
  - flat_hash.database._parse_data
  - metadata.database._parse_data
  - posixpath (os.path)

- Rework digest api to allow running checksums in parallel.
  Meaning: don't load the file three times for applying three checksums.
  Need to work out how to do this with fchksum and the "size" checksum.

- CONFIG_PROTECT unmerge support
- pkgcore.fetchable.__init__: __eq__/__hash__

- get the tree clean of direct /var/db/pkg access

- vdb2 format (ask harring for details).

- pkgcore.fs.ops.merge_contents; doesn't rewite the contents set when a file
  it's mergeing is relying on symlinked directories for the full path; eg,
  /usr/share/X11/xkb/compiled -> /var/blah, it records the former instead of 
  recording the true absolute path.

- pmerge exit code; ambiguousquery doesn't seem to result in ret != 0

- pmerge mods; [ --skip-set SET ] , [ --skip atom ], use similar restriction
  to --replace to prefer vdb for matching atoms

- info regeneration trigger; **

- refactor pkgcore.ebuild.cpv.ver_cmp usage to avoid full cpv parsing when 
  _cpv is in use; 
  'nuff said, look in pkgcore.ebuild.cpv.cpy_ver_cmp

- finish off trigger registration; **
  Right now it's hardcoded in merge.engine; this sucks, need to convert the 
  gentoo specific triggers over to being registered on the fly via
  domain/configuration.
  
- testing of fakeroot integration: **
  it was working back in the ebd branch days; things have changed since then 
  (heavily), enabling/disabling should work fine, but will need to take a look
  at the contentset generation to ensure perms/gid leaks through correctly.

- modify repository.prototype.tree.match to take an optional comparison *
  reasoning being that if we're just going to do a max, pass in the max so it 
  has the option of doing the initial sorting without passing through
  visibility filters (which will trigger metadata lookups)

- pkgcore.config.central features: ***
  These may or may not be picked off as development continues; the main
  requirement for this functionality is plugins, which the framework 
  intends... so... prior to a release, it will be added.

  - needs method to do lookups of further object restrictions/section_ref/etc
    from a common dir, based on name.  this one requires some thought;
    essentially, if loading portage-mysql.cache, try 1, or try this opt,
    look in a dir the plugins ebuild can install a section conf tweak, and
    use it.
  - configuration 'types' , list, bool, str, etc, should be extendable, lifted
    from a config most likely.  Defaults should be avail in code, but should
    have a method of extending it
  - integration of make.globals type data; defaults effectively, but a bit
    more complex.

- 'app bundles'.  Reliant on serious overhauling of deps to do 'locked deps',
  but think of it as rpath based app stacks, a full apache stack compiled to
  run from /opt/blah for example.

- pkgcore.ebuild.gpgtree ****
  derivative of pkgcore.ebuild.ebuild_repository, this overloads
  ebuild_factory and eclass_cache so that gpg checks are done.
  This requires some hackery, partially dependant on config.central changes
  (see above).  Need a way to specify the trust ring to use, 'severity' level
  (different class targets works for me).
  Anyone who implements this deserves massive cookies.

- pkgcore.ebuild.gpgprofile ****
  Same as above.

- pkgcore.fetch.bundled_lib:
  clean this beast up.

- IPV6 handling:
  bug 37124 # syncing
  check over BINHOST code replacement for any code that resolve to a specific
  IP

- locking unification.  see plugins for an example of why it's needed
