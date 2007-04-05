pquery usage
------------

Basics
======

pquery is used to extract various kinds of information about either installed or
uninstalled packages. As you probably guessed from the name it is similar to
equery, but it can do things equery cannot do and is a bit more flexible.

What pquery does is select packages from one or more "repositories" that match
a boolean combination of restrictions, then print selected information about
those packages. It is important to understand that the information printing and
repository selection options are almost completely separate from the
restriction options. The only exception to that is that restrictions on
contents automatically select the vdb (installed packages) repository, since
running them on the portdir repository makes no sense.

Another switch that could do with some extra explanation is --raw. Specifying
--raw makes your configuration not affect the results. Example: ::

 $ pquery --attr alldepends -m dbus --max -v
 * sys-apps/dbus-0.62-r1
     description: A message bus system, a simple way for applications to talk
                  to each other
     homepage: http://dbus.freedesktop.org/
     depends: >=dev-libs/glib-2.6 || ( ( x11-libs/libXt x11-libs/libX11 )
                  virtual/x11 ) >=x11-libs/gtk+-2.6 >=dev-lang/python-2.4
                  >=dev-python/pyrex-0.9.3-r2 >=dev-libs/expat-1.95.8
                  dev-util/pkgconfig sys-devel/automake
                  >=sys-devel/autoconf-2.59 sys-devel/libtool
     rdepends: >=dev-libs/glib-2.6 || ( ( x11-libs/libXt x11-libs/libX11 )
                  virtual/x11 ) >=x11-libs/gtk+-2.6 >=dev-lang/python-2.4
                  >=dev-python/pyrex-0.9.3-r2 >=dev-libs/expat-1.95.8
     post_rdepends:
 $

This is the highest unmasked package on my system. Also notice there are no
references to USE flags or qt in the dependencies. That is because I do not
have qt in USE in my configuration, so those dependencies do not apply.::

 $ pquery --attr alldepends -m dbus --max -v --raw
 * sys-apps/dbus-0.91
     description: Meta package for D-Bus
     homepage: http://dbus.freedesktop.org/
     depends:
     rdepends: >=sys-apps/dbus-core-0.91 python? (
                  >=dev-python/dbus-python-0.71 ) qt3? (
                  >=dev-libs/dbus-qt3-old-0.70 ) gtk? (
                  >=dev-libs/dbus-glib-0.71 ) !<sys-apps/dbus-0.91
     post_rdepends:
 $

This version is in package.mask, and we can see the use-conditional flags now.

The --verbose or -v flag tries to print human-readable output (although some
things like the formatting of depend strings need some improvement). Without -v
the output is usually a single line per package in a hopefully
machine-parseable format (usable in pipelines). There are some extras like
--atom meant for shell pipeline use. If you have some useful shell pipeline in
mind that pquery's output could be better formatted for please file a ticket.

Adding short options is planned but there are some features to add first (want
most of the features in place to avoid name clashes).

How Do I?
=========

============================ ========================================= ========================================================================
other tool                   pquery                                    comments
============================ ========================================= ========================================================================
``equery belongs /bin/ls``   ``pquery --owns /bin/ls``
``equery check``             not implemented (yet?)
``equery depends python``    ``pquery --vdb --revdep dev-lang/python`` omitting the ``--vdb`` makes it equivalent to ``equery depends -a``
``equery depgraph``          not implemented (yet?)
``equery files python``      ``pquery --contents -m python``           ``--contents`` is an output option, can be combined with any restriction
``equery hasuse python``     ``pquery --vdb --has-use python``
``equery list python``       ``pquery --vdb -m '*python*'``            this is in ExtendedAtomSyntax
``equery size``              ``not implemented (yet?)``
``equery uses python``       ``pquery --attr use -m python``           less information, but is an output option so mixes with any restriction
``emerge -s python``         ``pquery -vnm '*python*'``
``emerge -S python``         ``pquery -vnS python``                    searches through longdescription (from metadata.xml) too
No equivalent                ``pquery --license GPL-2 --vdb``          list all installed GPL-2 packages
No equivalent                ``pquery --maintainer seemant``           list all packages that are maintained by seemant
============================ ========================================= ========================================================================

It can also do some things equery/emerge do not let you do, like restricting
based on maintainer or herd and printing various other package attributes. See
--help for those. If you miss a query file a ticket.

Freeform Restrictions
=====================

One possibly interesting feature is:

``pquery --expr "and(or(herd(python), maintainer(me)), match('dev-*/*'))"``

which matches packages in a category starting with dev that are either
maintained by "me" or in the python herd. This code is not heavily tested and
the "not" boolean is currently broken. Should be fixed for the next release
though.
