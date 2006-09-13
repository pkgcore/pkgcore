=============================
 Trigger based functionality
=============================

Pkgcore internally uses triggers for all merge/unmerge actions- the reason for
this is mainly that of extensibility.  Different pkg managers will execute 
different things while merging files to the fs (or unmerging).

Via using hook/triggers internally, MergeEngine just operates on those lists- 
it just has to be properly configured, and it can handle everything itself.

The following is missing functionality in pkgcore that exists in portage, and 
must be reimplemented- studying ``pkgcore.merge.triggers`` is suggested 
prior to attempting it.  The protocol is *extremely* simple.

- config protect; unmerge mangling isn't implemented

- ``bin/ebuild-helpers/prepall`` functionality should be converted to trigger 
  based, and the call removed from dyn_install in 
  ``bin/ebuild-env/ebuild-default.sh``;
  This doesn't fly perfectly for ebuild calls.

- all QA checks from dyn_install need to be converted to triggers.
  This likely will require creation of a new cset; study 
  ``pkgcore.merge.engine.MergeEngine`` for examples of cset creation,
  for example get_merge_cset or get_livefs_intersect_cset

- pyo creation.  convert it to a post_modify trigger, which updates
  new_cset as it's going along.  This *will* interfere with existing ebuild
  solutions for it, but that is fine.

- .keep cleansing.  Portage creates .keep files in directories and utime's 
  the file so that it doesn't attempt to remove empty directories merged 
  during replace operations.  We'll need a post_modify scanner to clean
  those out.

- .keep creation.  see above, basically would be used when need to be
  compatible with portage


Additionally, fun functionality folks can hack on if they're bored- these 
will be optional.

- prelinking.  This is an optional trigger, but is implemented as a post_merge
  trigger.  No need to update the chksum for the file, although we will need
  a way to track that prelink'ing has occured.

- man/info page compression.  This can either be implemented as a post_modify 
  (yuck), or (cleanly) as an extension to merge_contents so that triggers can
  register callables to do the actual copying to the livefs.

  This is a bit tricky when it comes to fs symlinking of files.

- size sanity_check prior to attempting the merge; this will be tricky since 
  it requires figuring out all mounts and space available for each.

- icon cache trigger for fd.o spec; specifically, touching the icon directory mtime
  to force any consumers of the icon cache to flush their cache and start anew.
