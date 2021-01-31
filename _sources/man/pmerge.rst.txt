======
pmerge
======

.. include:: pmerge/_synopsis.rst
.. include:: pmerge/_description.rst

Portage Compatibility
=====================

With regards to portage compatibility, pmerge provides much of the same
functionality that **emerge**\(1) does. In general, it should be possible to use
both pmerge and emerge on the same system in a sane fashion. For example,
pmerge can be used to install packages and then emerge should be able to
upgrade or uninstall them, or vice versa. Also, binary packages created using
pmerge should be able to be installed properly using emerge. Any major
compatibility issue that arises when trying to use both package managers is
probably a bug and should be reported.

In terms of option naming, pmerge tries to remain somewhat compatible to
portage so running ``pmerge -1av`` should work the same as ``emerge -1av`` when
using portage. However, pmerge doesn't implement nearly the same amount of
options that portage provides so many of the more obscure ones are missing. In
addition, pmerge defaults to a portage compatible output format that closely
matches the default colors and output structure that portage uses.

.. include:: pmerge/_options.rst
.. include:: pmerge/_subcommands.rst

Example Usage
=============

Merge pkgcore from the gentoo repo::

    pmerge sys-apps/pkgcore::gentoo

Output a simple list of package atoms that would be updated for a global
update::

    pmerge -uDp --formatter basic @world

Force new binpkgs to be built for the entire system set using a custom
configuration directory::

    pmerge -uDSeb --config /home/foo/portage @system

See Also
========

**emerge**\(1)
