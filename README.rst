|pypi| |test| |coverage|

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

At least python version 3.8, and snakeoil_ — a utility library split out of
pkgcore for others to use.

Installing
==========

Installing latest pypi release::

    pip install pkgcore

Installing from git::

    pip install https://github.com/pkgcore/pkgcore/archive/master.tar.gz

Installing from a tarball::

    python setup.py install

Tests
=====

A standalone test runner is integrated in setup.py; to run, just execute::

    python setup.py test

In addition, a tox config is provided so the testsuite can be run in a
virtualenv setup against all supported python versions. To run tests for all
environments just execute **tox** in the root directory of a repo or unpacked
tarball. Otherwise, for a specific python version execute something similar to
the following::

    tox -e py39

Docs
====

Documentation is available on Github_.

Contact
=======

For bugs and feature requests please create an issue_.


.. _Github: https://pkgcore.github.io/pkgcore/
.. _snakeoil: https://github.com/pkgcore/snakeoil
.. _issue: https://github.com/pkgcore/pkgcore/issues

.. |pypi| image:: https://img.shields.io/pypi/v/pkgcore.svg
    :target: https://pypi.python.org/pypi/pkgcore
.. |test| image:: https://github.com/pkgcore/pkgcore/workflows/test/badge.svg
    :target: https://github.com/pkgcore/pkgcore/actions?query=workflow%3A%22test%22
.. |coverage| image:: https://codecov.io/gh/pkgcore/pkgcore/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/pkgcore/pkgcore
