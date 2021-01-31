===========
Ebuild EAPI
===========


This should hold the proposed (with a chance of making it in), accepted, and
implemented changes for ebuild format version 1.  A version 0 doc would also
be a good idea ( no one has volunteered thus far ).

Version 0 (or undefined eapi, <=portage-2.0.52*)]
*************************************************

Version 1
*********

This should be fairly easy stuff to implement for the package manager,
so this can actually happen in a fairly short timeframe.

- EAPI = 1 required
- src_configure phase is run before src_compile. If the ebuild or
  eclass does not override there is a default that does nothing.
  Things like econf should be run in this phase, allowing rerunning
  the build phase without rerunning configure during development.
- Make the default implementation of phases/functions available under
  a second name (possibly using EXPORT_FUNCTIONS) so you can call
  base_src_compile from your src_compile.
- default src_install. Exactly what goes in needs to be figured out,
  see bug 33544.
- RDEPEND="${RDEPEND-${DEPEND}}" is no longer set by portage, same for eclass.
- (proposed) BDEPEND metadata addition, maybe. These are the
  dependencies that are run on the build system (toolchain, autotools
  etc). Useful for ROOT != "/". Probably hard to get right for ebuild
  devs who always have ROOT="/".
- default IUSE support, IUSE="+gcj" == USE="gcj" unless the user disables it.
- GLEP 37 ("Virtuals Deprecation"), maybe. The glep is "deferred". How
  much of this actually needs to be done? package.preferred?
- test depend, test src_uri (or represent test in the use namespace
  somehow). Possibilities: TEST_{SRC_URI,{B,R,}DEPEND}, test "USE"
  flag getting set by FEATURES=test.
- drop AA (unused).
- represent in metadata if the pkg needs pkg_preinst to have access to
  ${D} or not. If this is not required a binpkg can be unpacked
  straight to root after pkg_preinst. If pkg_preinst needs access to
  ${D} the binpkg is unpacked there as usual.
- use groups in some form (kill use_expand off).
- ebuilds can no longer use PORTDIR and ECLASSDIR(s); they break any
  potential remote, and are dodgey as all hell for multiple repos
  combined together.
- disallow direct access to /var/db/pkg
- deprecate ebuild access/awareness of PORTAGE_* vars; perl ebuilds
  security fix for PORTAGE_TMPDIR (rpath stripping in a way) might
  make this harder.
- use/slot deps, optionally repository deps.
- hard one to slide in, but change versioning rules; no longer allow
  1.006, require it to be 1.6
- pkg_setup must be sandboxable.
- allowed USE conditional configurations; new metadata key, extend
  depset syntax to include xor, represent allowed configurations.
- true incremental stacking support for metadata keys between
  eclasses/ebuilds; RESTRICT=-strip for example in the ebuild.
- drop -* from keywords; it's package.masking, use that instead (-arch
  is acceptable although daft)
- blockers aren't allowed in PDEPEND (the result of that is serious
  insanity for resolving)

Version 1+
**********

Not sure about these. Maybe some can go into version 1, maybe they
will happen later.

- Elibs
- some way to 'bind' a rdep/pdep so that it's explicit "I'm locked
  against the version I was compiled against"
- some form of optional metadata specifying that a binpkg works on
  multiple arches, iow it doesn't rely on compiled components.
- A way to move svn/cvs/etc source fetching over to the package
  manager. The current way of doing this through an eclass is a bit
  ugly since it requires write access to the distdir. Moving it to the
  package manager fixes that and allows integrating it with things
  like parallel fetch. This needs to be fleshed out.
