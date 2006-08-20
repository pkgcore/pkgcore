===========
Ebuild EAPI
===========


This should hold the proposed (with a chance of making it in), accepted, and 
implemented changes for ebuild format version 1.  A version 0 doc would also
be a good idea ( no one has volunteered thus far ).

Version 0 (or undefined eapi, <=portage-2.0.52*)]
*************************************************

Version 1
*************************************************
- EAPI = 1 required
- src_configure exists, configuration of packages must occur in src_configure
  and not src_compile. 
- default src_install
- RDEPEND="${RDEPEND-${DEPEND}}" is no longer set by portage, same for eclass.
- Elibs
- (proposed) BDEPEND metadata addition ?
- default IUSE support, IUSE="+gcj" == USE="gcj" unless the user disables it.
- GLEP 37
- test depend, test src_uri (or represent test in the use namespace somehow)
- drop AA (unused)
- some form of optional metadata specifying that a binpkg works on multiple arches, iow it doesn't rely on compiled components.
- represent in metadata if the pkg needs pkg_preinst to have access to ${D} or not; forced unpacking sucks.
- some way to 'bind' a rdep/pdep so that it's explicit "I'm locked against the version I was compiled against"
- use groups in some form.
- drop reliance on PORTDIR and ECLASSDIR(s); they break any potential remote, and are dodgey as all hell for multiple
  repos combined together.
- deprecate ebuild access/awareness of PORTAGE_* vars; perl ebuilds security fix for PORTAGE_TMPDIR (rpath stripping in a way) 
  might make this harder.
- use/slot deps, optionally repository deps.
- hard one to slide in, but change versioning rules; no longer allow 1.006, require it to be 1.6
