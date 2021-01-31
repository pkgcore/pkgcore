=========
 Changes
=========

(Note that this is not a complete list)

* Proper env saving/reloading. The ebuild is sourced once, and run from the env.
* DISTDIR has indirection now. It points at a directory, ie, symlinks.
  to the files. The reason for this is to prevent builds from lying about their
  sources, leading to less bugs.
* PORTAGE_TMPDIR is no longer in the ebuild env.
* (PORTAGE_|)BUILDDIR is no longer in the ebuild env.
* BUILDPREFIX is no longer in the ebuild env.
* AA is no longer in the ebuild env.
* inherit is an error in phases except for setup, prerm, and postrm.
  pre/post rm are allowed only in order to deal with broken envs. Running
  config with a broken env isn't allowed, because config won't work;
  installing with a broken env is not allowed because preinst/postinst
  won't be executed.
* binpkg building now gets the unmodified contents- thus when merging a
  binpkg, all files are there unmodified.
