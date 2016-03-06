|pypi| |test| |coverage| |docs|

=======
pkgcore
=======

pkgcore is a framework for package management; via the appropriate class
plugins, the design should allow for any underlying repository/config/format to
be used; slackware's tgzs being exempted due to lack of any real metadata, and
autopackage format being exempted due to the fact they effectively embed the
manager in each package (pkgcore *does* require being able to treat the pkg as
data, instead of autopackage's method of handing resolution/all manager ops off
to the package script).

Tools
=====

**pclean**: clean distfiles, binpkgs, and builds dirs

**pclonecache**: clone a repository cache

**pconfig**: query configuration info

**pebuild**: low-level ebuild operations, go through phases manually

**pinspect**: inspect repository related info

**pmaint**: repository maintenance (syncing, copying...)

**pmerge**: dependency resolution, fetching, (un)merging, etc.

**pquery**: query repository info, revdeps, pkg search, vdb search, etc.

Requirements
============

At least python version 2.7, and snakeoil_ — a utility library with misc
optimizations split out of pkgcore for others to use.  For unittests, mock_ is
required if you're using anything less than python 3.3.

Installing
==========

Installing latest pypi release in a virtualenv::

    pip install pkgcore

Installing from git in a virtualenv (note that snakeoil should be used from git)::

    pip install https://github.com/pkgcore/snakeoil/archive/master.tar.gz
    pip install https://github.com/pkgcore/pkgcore/archive/master.tar.gz

Installing from a tarball or git repo::

    python setup.py install
    pplugincache

Documentation
=============

Official documentation is provided on readthedocs_ with alternative
formats available for download_.

Tests
=====

A standalone test runner is integrated in setup.py; to run, just execute::

    python setup.py test

In addition, a tox config is provided so the testsuite can be run in a
virtualenv setup against all supported python versions. To run tests for all
environments just execute **tox** in the root directory of a repo or unpacked
tarball. Otherwise, for a specific python version execute something similar to
the following::

    tox -e py27

Contact
=======

For support and development inquiries join `#pkgcore`_ on Freenode.

For bugs and feature requests please create an issue on Github_.


.. _snakeoil: https://github.com/pkgcore/snakeoil
.. _Github: https://github.com/pkgcore/pkgcore/issues
.. _#pkgcore: https://webchat.freenode.net?channels=%23pkgcore&uio=d4
.. _introduction docs: http://pkgcore.readthedocs.org/en/latest/getting-started.html
.. _development docs: http://pkgcore.readthedocs.org/en/latest/dev-notes/developing.html
.. _readthedocs: http://pkgcore.readthedocs.org/
.. _download: https://readthedocs.org/projects/pkgcore/downloads/
.. _mock: https://pypi.python.org/pypi/mock

.. |pypi| image:: https://img.shields.io/pypi/v/pkgcore.svg
    :target: https://pypi.python.org/pypi/pkgcore
.. |test| image:: https://travis-ci.org/pkgcore/pkgcore.svg?branch=master
    :target: https://travis-ci.org/pkgcore/pkgcore
.. |coverage| image:: https://coveralls.io/repos/pkgcore/pkgcore/badge.png?branch=master
    :target: https://coveralls.io/r/pkgcore/pkgcore?branch=master
.. |docs| image:: https://readthedocs.org/projects/pkgcore/badge/?version=latest
    :target: http://pkgcore.readthedocs.org/
    :alt: Documentation Status
