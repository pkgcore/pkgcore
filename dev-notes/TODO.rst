==========
Rough TODO
==========

- rip out use.* code from pkgcore_checks.addons.UseAddon.__init__, and 
  generalize it into pkgcore.ebuild.repository

- not hugely important, but... make a cpython version of SlottedDict from
  pkgcore.util.obj; 3% reduction for full repo walk, thus not a real huge
  concern atm.

- userpriv for pebuild misbehaves..

- http://aspn.activestate.com/ASPN/Cookbook/Python/Recipe/491285
  check into, probably better then my curfty itersort; need to see how
  well heapqu's nlargest pop behaves (looks funky)
  
- look into converting MULTILIB_STRICT* crap over to a trigger

- install-sources trigger

- recreate verify-rdepends also

- observer objects for reporting back events from merging/unmerging
  cpython 'tee' is needed, contact harring for details.
  basic form of it is in now, but need something more powerful for 
  parallelization
  elog is bound to this also

- Possibly convert to cpython:

  - flat_hash.database._parse_data
  - metadata.database._parse_data
  - posixpath (os.path)

- get the tree clean of direct /var/db/pkg access

- vdb2 format (ask harring for details).

- pkgcore.fs.ops.merge_contents; doesn't rewite the contents set when a file
  it's mergeing is relying on symlinked directories for the full path; eg,
  /usr/share/X11/xkb/compiled -> /var/blah, it records the former instead of 
  recording the true absolute path.

- pmerge mods; [ --skip-set SET ] , [ --skip atom ], use similar restriction
  to --replace to prefer vdb for matching atoms

- refactor pkgcore.ebuild.cpv.ver_cmp usage to avoid full cpv parsing when 
  _cpv is in use; 
  'nuff said, look in pkgcore.ebuild.cpv.cpy_ver_cmp

- testing of fakeroot integration

  it was working back in the ebd branch days; things have changed since then 
  (heavily), enabling/disabling should work fine, but will need to take a look
  at the contentset generation to ensure perms/gid leaks through correctly.

- modify repository.prototype.tree.match to take an optional comparison

  reasoning being that if we're just going to do a max, pass in the max so it 
  has the option of doing the initial sorting without passing through
  visibility filters (which will trigger metadata lookups)

- 'app bundles'.  Reliant on serious overhauling of deps to do 'locked deps',
  but think of it as rpath based app stacks, a full apache stack compiled to
  run from /opt/blah for example.

- pkgcore.ebuild.gpgtree

  derivative of pkgcore.ebuild.ebuild_repository, this overloads
  ebuild_factory and eclass_cache so that gpg checks are done.
  This requires some hackery, partially dependant on config.central changes
  (see above).  Need a way to specify the trust ring to use, 'severity' level
  (different class targets works for me).
  Anyone who implements this deserves massive cookies.

- pkgcore.ebuild.gpgprofile: 
  Same as above.

- reintroduce locking of certain high level components using read/write;
  mainly, use it as a way to block sync'ing a repo that's being used to build, 
  lock the vdb for updates, etc.
