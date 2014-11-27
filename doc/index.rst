.. pkgcore documentation master file, created by
   sphinx-quickstart on Sun Aug  1 16:23:57 2010.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

Welcome to pkgcore's documentation!
===================================

pkgcore is a framework for package management; via the appropriate class plugins,
the design should allow for any underlying repository/config/format to be used;
slackwares tgzs being exempted due to lack of any real metadata, and
autopackage format being exempted due to the fact they effectively embed the
manager in each package (pkgcore *does* require being able to treat the pkg as
data, instead of autopackages method of handing resolution/all manager ops off
to the package script).

Official source code repository: `pkgcore <https://github.com/pkgcore/pkgcore>`_

Contents:

.. toctree::
   :titlesonly:
   :maxdepth: 1

   getting-started
   news
   api
   man
   dev-notes

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
