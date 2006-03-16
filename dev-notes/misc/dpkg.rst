======
 dpkg
======

this is just *basic* notes, nothing more. If you know details, fill in
the gaps kindly

repos are combined.

Sources.gz
  (list of source based deb's) holds name, version, and build deps.

Packages.gz
  (binary debs, dpkgs)
  name, version, size, short and long description, bindeps.

repository layout::

	dists
		stable
			main
				arch #binary-arm fex
				source #?
			contrib #?
				arch # binary-arm fex
				source
			non-free # guess.
				arch
				source
		testing...
		unstable...

arch/binary-* dirs hold Packages.gz, and Release (potentially)
source dirs hold Sources.gz and Release (optionally)

has preinst, postinst, prerm, postrm
Same semantics as ebuilds in terms of when to run (coincidence? :)

==============  ==========================================
in dpkg         in ebuild
==============  ==========================================
Build-Depends   our DEPEND
Depends         our RDEPEND
Pre-Depends     configure time DEPEND
Conflicts       blockers, affected by Essential
                (read up on this in debian policy guide)
==============  ==========================================