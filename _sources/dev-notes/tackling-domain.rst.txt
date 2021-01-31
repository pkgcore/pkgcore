=================
 Tackling domain
=================

tag a 'x' in front of stuff that's been implemented

unhandled (eg, figure these out) vars/features

- (user)?sandbox
- digest
- cvs (this option is a hack)
- fixpackages , which probably should be a sync thing (would need to
  bind the vdb and binpkg repo to it though)
- keep(temp|work), easy to implement, but where to define it?
- PORT_LOGDIR
- env overrides of use...

vdb wrapper/vdb repo instantiation (either domain created wrapper, or
required in the vdb repo section def)

- CONFIG_PROTECT*
- collision-protect
- no(doc|man|info|clean) (wrapper/mangler)
- suidctl
- nostrip. in effect, strip defaults to on; wrappers if after
  occasionally on, occasionally off.
- sfperms

build section (vars)

- C(HOST|TARGET), (LD*|C*)FLAGS?
- (RESUME|FETCH)COMMAND are fetcher things, define it there.
- MAKEOPTS
- PORTAGE_NICENESS (imo)
- TMPDIR ?  or domain it?

gpg is bound to repo, class type specifically. strict/severe are
likely settings of it. the same applies for profiles.

distlocks is a fetcher thing, specifically (probably) class type.

buildpkgs is binpkg + filters.

package.provided is used to generate a seperate vdb, a null vdb that
returns those packages as installed.
