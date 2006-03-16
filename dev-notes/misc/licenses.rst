==========
 Licenses
==========

Hokay, just added license support; issue with it's implementation
though, there's no negation yet. currently it's effectively for the
filter::

  not ( licenses in $ACCEPT_LICENSES || licenses in package.license )

To support negation, needs to be::

  not ( licenses in package.license || (
    licenses in $ACCEPT_LICENSES &&
    not licenses in (filtered) package.license ) )

so... anyone after getting it added (I'll do it when I get around to
it), poke in ``pkgcore.config.domain.domain``.
