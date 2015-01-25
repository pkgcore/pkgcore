======
pmerge
======

.. include:: pmerge/main_synopsis.rst

Description
===========

pmerge is the main command-line utility for merging and unmerging packages on a
system. It provides an interface to install, update, and uninstall ebuilds from
source or binary packages.

Portage Compatibility
=====================

With regards to portage compatibility, pmerge provides much of the same
functionality that *emerge* does. In general, it should be possible to use
both pmerge and emerge on the same system in a sane fashion. For example,
pmerge can be used to install packages and then emerge should be able to
upgrade or uninstall them, or vice versa. Also, binary packages created using
pmerge should be able to be installed properly using emerge. Any major
compatibility issue that arises when trying to use both package managers is
probably a bug and should be reported.

In terms of option naming, pmerge tries to remain somewhat compatible to
portage so running "pmerge -1av" should work the same as "emerge -1av" when
using portage. However, pmerge doesn't implement nearly the same amount of
main_options that portage provides so many of the more obscure ones are missing. In
addition, pmerge defaults to a portage compatible output format that closely
matches the default colors and output structure that portage uses.

.. include:: pmerge/main_options.rst

See Also
========

emerge(1), pmaint(1), pebuild(1), pquery(1)
