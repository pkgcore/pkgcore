========
 pquery
========

------------------
Query repositories
------------------

:Date:   2007-02-18
:Manual section: 1
:Manual group: text processing

SYNOPSIS
========

  pquery [options]

DESCRIPTION
===========

pquery is the query tool for the pkgcore framework.  Via it, you can search
on arbitrary metadata, do --blame lookup (maintainer/herds), license queries,
revdep lookups, environment lookups (look for a variable set in the environment
of a merged vdb package), search based on herd, maintainer, etc.

OPTIONS
=======

.. pkgcore_script_options:: pkgcore.scripts.pquery.OptionParser
