====================
 Getting a bzr repo
====================

If you're just installing pkgcore from a released tarball, skip this section.

The quickest way to get a copy of the integration (release) branch is via
downloading
http://dev.gentooexperimental.org/~pkgcore/pkgcore-current.tar.gz

This does not have history. To get history, bzr get
http://dev.gentooexperimental.org/~pkgcore/bzr/pkgcore. If this is too
slow please let someone in #pkgcore know so we can put up a tarball
with history again.

====================
 Installing pkgcore
====================

Set PYTHONPATH
==============

Set PYTHONPATH to include your pkgcore directory, so that python can find the
pkgcore code. Fore example::

 $ export PYTHONPATH="${PYTHONPATH}:/home/user/pkgcore/"

Now test to see if it works::

 $ python -c'import pkgcore'

Python will scan pkgcore, see the pkgcore directory in it (and that it has
__init__.py), and use that.


Registering plugins
===================

Pkgcore uses plugins for some basic functionality. You do not really
have to do anything to get this working, but things are a bit faster
if the plugin cache is up to date. This happens automatically if the
cache is stale and the user running pkgcore may write there, but if
pkgcore is installed somewhere system-wide and you only run it as user
you can force a regeneration with::

 # python -c \
     'from pkgcore import plugin2, plugins; plugin2.initialize_cache(plugins)

A friendly utility to do this is planned.

Test pkgcore
============

Drop back to normal user, and try::

 $ python
 >>> import pkgcore.config
 >>> from pkgcore.ebuild.atom import atom
 >>> conf=pkgcore.config.load_config()
 >>> tree=conf.get_default('domain').repos[1]
 >>> pkg=max(tree.itermatch(atom("dev-util/diffball")))
 >>> print pkg
 >>> print pkg.depends
 >=dev-libs/openssl-0.9.6j >=sys-libs/zlib-1.1.4 >=app-arch/bzip2-1.0.2


At the time of writing the domain interface is in flux, so this example might
fail for you. If it doesn't work ask for assistance in #pkgcore on freenode,
or email ferringb (at) gmail.com' with the traceback.

Build filter-env
================

Finally, you need filter-env for the ebuild daemon::

 $ python setup.py build_filter_env
