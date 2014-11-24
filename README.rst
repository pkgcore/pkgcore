=======
pkgcore
=======

What is pkgcore?
================

pkgcore is a framework for package management; via the appropriate class
plugins, the design should allow for any underlying repository/config/format to be used;
slackwares tgzs being exempted due to lack of any real metadata, and
autopackage format being exempted due to the fact they effectively embed the
manager in each package (pkgcore *does* require being able to treat the pkg as
data, instead of autopackages method of handing resolution/all manager ops off
to the package script).


What does pkgcore require?
==========================

At least python verison 2.7, and `snakeoil <https://github.com/pkgcore/snakeoil>`_ - snakeoil is a utility library with
misc optimizations split out of pkgcore for others to use.


Who to contact if I find a bug?
===============================

Please submit an issue via `Github <https://github.com/pkgcore/pkgcore/issues>`_. Please do not
use `Gentoo Bugzilla <https://bugs.gentoo.org>`_ as the first step; any bugs, pkgcore devs should filter
before passing up at this point.

You can also stop by at `#pkgcore <https://webchat.freenode.net?channels=%23pkgcore&uio=d4>`_  on Freenode.


Tools
=====

**pclone_cache**: clone a repository cache

**pebuild**: low-level ebuild operations, go through phases manually

**pinspect**: generic utility for inspecting repository related info

**pmaint**: generic utility for repository maintenance (syncing, copying...)

**pmerge**: generic utility for doing resolution, fetching, merging/unmerging,
etc.

**pquery**: generic utility for querying info about repositories, revdeps, pkg
search, vdb search, etc.


Documentation
=============

Please take a look at either doc/ and dev-notes/ ; additionally, the code for
the most part has docstrings, thus pydoc is a good reference.

doc/getting-started.rst is a good introduction if you're just getting started.
If you want to start hacking, take a look at dev-notes/developing.rst.

In addition, html documentation is available at
http://api.pkgcore.org/pkgcore/, as is postscript and pdf.


Tests
=====

A standalone test runner is integrated in setup.py; to run, just execute
setup.py test
Aside from that, our runner of choice is twisted's trial; ran via::

    trial pkgcore

If you're doing development, trial is significantly friendlier; the standalone
runner is designed to be mainly used for installations of pkgcore, where
all tests must pass, else installation is aborted.


Installing
==========

To build::

    tar jxf pkgcore-0.XX.tar.bz2
    cd pkgcore-0.XX
    python setup.py build

Run tests::

    cd pkgcore-0.xx
    python setup.py test
     or
    trial pkgcore

To install::

    cd pkgcore-0.xx
    python setup.py install
    pplugincache
