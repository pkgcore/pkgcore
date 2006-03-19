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
- RDEPEND="${RDEPEND-${DEPEND}}" is no longer set by portage.
- Elibs
- (proposed) BDEPEND metadata addition.
- default IUSE support, IUSE="+gcj" == USE="gcj" unless the user disables it.
- GLEP 37
- test depend, test src_uri
