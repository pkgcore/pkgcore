===========
 perl CPAN
===========

* makeCPANstub in Gentoo/CPAN.pm , dumps cpan config
* screen scraping to get deps, example page http://kobesearch.cpan.org/,
  use getCPANInfo from CPAN
* use FindDeps for this
* use unmemoize(func) to back out the memoizing of a func; do this on FindDeps
