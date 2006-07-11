====================
 Installing pkgcore
====================

Set PYTHONPATH
==============

Set PYTHONPATH to include your pkgcore directory, so that python can find the
pkgcore code. Fore example::

 # export PYTHONPATH="${PYTHONPATH}:/home/user/pkgcore/"

Now test to see if it works::

 # python -c'import pkgcore'

Python will scan pkgcore, see the pkgcore directory in it (and that it has
__init__.py), and use that.


Registering plugins
===================

Pkgcore is pluggable, so even to get the basis working some plugins must be
registered by running as root::

 # pkgcore/bin/utilities/register.bash

If you register plugins manually you need to set PYTHONPATH (note that sudo
cleanses the env normally).  If that fails, your PYTHONPATH is invalid;
if it works it'll spit back a registering message.  So far, good to go.

Test pkgcore
============

Drop back to normal user, and try::

 # python
 >>> import pkgcore.config
 >>> conf=pkgcore.config.load_config()
 >>> tree=conf.get_default('domain').repos[1]
 >>> pkg=tree["dev-util/diffball-0.6.5"]
 >>> print pkg.depends
 >=dev-libs/openssl-0.9.6j >=sys-libs/zlib-1.1.4 >=app-arch/bzip2-1.0.2


At the time of writing the domain interface is in flux, so this example might
fail for you. If it doesn't work ask for assistance in #pkgcore on freenode,
or email ferringb (at) gmail.com' with the traceback.

Build filter-env
================

Finally, you need filter-env for the ebuild daemon:

 #python setup.py build_filter_env
