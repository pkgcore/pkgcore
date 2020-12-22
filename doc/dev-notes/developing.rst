=========================
 Checking the source out
=========================

If you're just installing pkgcore from a released tarball, skip this section.

To get the current (development) code with history, install git
(``emerge git`` on gentoo) and run::

  git clone git://github.com/pkgcore/pkgcore.git

====================
 Installing pkgcore
====================

Set PYTHONPATH
==============

If you only want to run scripts from pkgcore itself (the ones in its
"bin" directory) you do not have to do anything with PYTHONPATH. If
you want to use pkgcore from an interactive python interpreter session
you do not have to do anything if you start the interpreter from the
"root" of the pkgcore source tree. For other uses you probably want to
set PYTHONPATH to include your pkgcore directory, so that python can
find the pkgcore code. For example::

 $ export PYTHONPATH="${PYTHONPATH}:/home/user/pkgcore/"

Now test to see if it works::

 $ python -c 'import pkgcore'

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

 # pplugincache

If you want to update plugin caches for something other than pkgcore's
core plugin registry, pass the package name as an argument.

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
fail for you.

Build extensions
================

If you want to run pkgcore from its source directory but also want the
extra speed from the compiled extension modules, compile them in place::

 $ python setup.py build_ext -i
