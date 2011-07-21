========
Overview
========

Pkgcore supports several configuration formats, Portage's ``/etc/make.conf``
included. This file documents the current state of the support.

FEATURES
========

Supported:

* ccache
* distcc
* sandbox
* usersandbox
* userpriv
* test
* nodoc
* noinfo
* noman
* userfetch (forced on)
* collision-protect
* metadata-transfer (does not do the actual transfer however)
* nostrip

Partially supported:

* strict (mostly there, just missing a few additions)

Unsupported digest-related:

* assume-digests
* cvs
* digest

Unsupported misc:

* severe
* keeptemp
* keepwork
* distlocks
* selinux
* sesandbox (selinux context sandbox)
* fixpackages
* notitles

Unsupported, unlikely to be implemented:

* noauto  (too tool-specific)
* mirror  (it's possible to implement it via a custom fetcher,
           but there are better ways; use ``mirror-dist`` if you want a mirror)
* lmirror (same)

Aside from that... everything else make.conf wise should be supported with
out issue- if not, please open a ticket at http://pkgcore.org/

For ``/etc/portage/``, we don't support modules (define custom cache modules)
due the fact our cache subsystem has grown a bit beyond what got imported into
Portage in 2.1; additionally, we do not support ``package.provided``.


For ``/etc/portage/package.*`` files, we support an extended atom syntax which
can be used in place of normal atoms (It goes without saying Portage doesn't
support the extension yet, thus introducing incompatibility if used) - read
extended-atom-syntax.rst for the details.
