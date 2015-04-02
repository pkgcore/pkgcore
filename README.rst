|pypi| |test| |coverage| |docs|

What is pkgcore?
================

pkgcore is a framework for package management; via the appropriate class
plugins, the design should allow for any underlying repository/config/format to
be used; slackware's tgzs being exempted due to lack of any real metadata, and
autopackage format being exempted due to the fact they effectively embed the
manager in each package (pkgcore *does* require being able to treat the pkg as
data, instead of autopackage's method of handing resolution/all manager ops off
to the package script).


What does pkgcore require?
==========================

At least python version 2.7, and snakeoil_ — a utility library with misc
optimizations split out of pkgcore for others to use.  For unittests, mock_ is
required if you're using anything less than python 3.3.


Who to contact if I find a bug?
===============================

Please submit an issue via Github_. You can also stop by at `#pkgcore`_ on
Freenode.


Tools
=====

**pclonecache**: clone a repository cache

**pebuild**: low-level ebuild operations, go through phases manually

**pinspect**: generic utility for inspecting repository related info

**pmaint**: generic utility for repository maintenance (syncing, copying...)

**pmerge**: generic utility for doing dependency resolution, fetching,
(un)merging, etc.

**pquery**: generic utility for querying info about repositories, revdeps, pkg
search, vdb search, etc.


Documentation
=============

Please take a look at either doc/ and dev-notes/ ; additionally, the code for
the most part has docstrings, thus pydoc is a good reference.

The `introduction docs`_ are good if you're just getting started. If you want
to start hacking, take a look at the `development docs`_.

In addition, html documentation is available at readthedocs_, alternative
formats are also available for download_.


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


Installing
==========

To build::

    tar jxf pkgcore-0.XX.tar.bz2
    cd pkgcore-0.XX
    python setup.py build

To install::

    cd pkgcore-0.xx
    python setup.py install
    pplugincache


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
    :target: https://readthedocs.org/projects/pkgcore/?badge=latest
    :alt: Documentation Status
