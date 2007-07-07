Atom Syntax
===========

pkgcore supports an extended form of atom syntax- examples are provided below.

This form can be used in configuration files, but in doing so portage will have
issues with the syntax, so if you want to maintain configuration
compatibility, limit your usage of the extended syntax to the commandline only.

===============  =========================================================
token            result
===============  =========================================================
*                match all
portage          package name must be ''portage''
dev-util/*       category must be ''dev-util''
dev-*/*          category must start with ''dev-''
dev-util/*       category must be ''dev-util''
dev-*            package must start with ''dev-''
*cgi*            package name must have ''cgi'' in it
*x11*/X*         category must have ''x11'' in it, package must start with
                 ''X''
*-apps/portage*  category must end in ''-apps'', package must start with
                 ''portage''
=portage-1.0     match version 1.0 of any 'portage' package
===============  =========================================================


Additionally, pkgcore supports additional atom extensions that are more
'pure' to the atom specification.


Use Dep atoms
-------------

http://bugs.gentoo.org/2272 has the details, but a use dep atom is basically a
normal atom that is able to force/disable flags on the target atom.  Portage
currently doesn't support use deps, although pkgcore and paludis do.

Note: Although paludis supports use deps, the syntax is different to what
pkgcore uses.

Syntax:

  normal-atom[enabled_flag1,enabled_flag2,-disabled_flag,-disabled_flag2]

Example:

  sys-apps/portage[build]

Would only match sys-apps/portage with the build flag forced on.

Forcing 'build' off while forcing 'doc' on would be:

  sys-apps/portage[-build,doc]


Slot dep atoms
--------------

Slot dep atoms allow for finer grained matching of packages- portage as of
2.1.2 supports them, but they're currently unable to be used in the tree.

Syntax:

  normal-atom:slot1,slot2,slot3

Matching just python in slot '2.3':

  dev-lang/python:2.3

Matching python in slot '2.3' or '2.4'

  dev-lang/python:2.3,2.4


repo_id atoms
-------------

The main usage of this form is to limit an atom to match only within a specific
repository - for example, to state "I need python from the gentoo-x86
repository _only_"

syntax:

  normal-atom::repository-id

Example:

  sys-devel/gcc::gentoo

A complication of this form is that ':' is also used for slots- '::' is treated
as strictly repository id matching, and must be the last token in the atom.

If you need to do slot matching in addition, it would be

  sys-devel/gcc:3.3:gentoo

which would match slot '3.3' from repository 'gentoo' (defined in
profiles/repo_name) of sys-devel/gcc.
