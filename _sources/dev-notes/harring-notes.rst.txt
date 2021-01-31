resolver
========

Current design doesn't coalesce- expects that each atom as it's passed in
specifies the dbs, which is how it does it's update/empty-tree trickery.

This isn't optimal.  Need to flag specific atoms/matches as "upgrade if
possible" or "empty tree if possible", etc; via this, we get coalescing
behaviour.  Specifically, if the targets are git[subversion] and subversion,
we want both upgraded.  So when resolving git[subversion] and encountering
dev-util/subversion, we should aim for upgrading it per the commandline request.

Additional question- should we apply this coalescing awareness to intermediate atoms
along the way resolution wise?  specifically, the cnf/dnf solutions, grabbing those
and stating "yeah, collapse to these if possible since they're likely required" ?


resolver redesign
=================

Hate to say it, but should go back to a specific 'resolve' method w/ the
resolver plan object holding targets- reason being, we may have to backtrack
the whole way.


config/use issues
=================

need to find a way to clone a stack, getting a standalone config stack if
possible for the resolver- specifically so it can do resets as needed, track
what is involved (use dep forcing) w/out influencing preexisting access to
that tree, nor being affected by said usage.
