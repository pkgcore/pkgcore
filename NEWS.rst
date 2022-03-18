=============
Release Notes
=============

----------------------------
pkgcore 0.12.10 (2022-03-18)
----------------------------

- pkgcore.ebuild.repository: support inheriting use_expand_desc
  and deprecated

- pkgcore.ebuild.eclass: support @ECLASS_VARIABLE as a modern spelling
  for @ECLASS-VARIABLE

---------------------------
pkgcore 0.12.9 (2021-12-14)
---------------------------

- ebd: fix unpack command not working if called via pebuild(1)

- pmerge: make failure output more readable via color coding

- ebd: update ``econf`` in EAPI 8 to pass ``--disable-static``
  as specified by the updated version of PMS

- pkgcore.sync.http: fix incorrect TLS context

---------------------------
pkgcore 0.12.8 (2021-09-26)
---------------------------

- ebd: fix PIPESTATUS verification for assert

- pkgcore.ebuild.eclass: add ABI_VERSION attribute to EclassDoc
  to improve future compatibility between pkgcheck and pkgcore

- pkgcore.ebuild.profiles: do not emit errors for profiles deprecated
  without a replacement

---------------------------
pkgcore 0.12.7 (2021-09-03)
---------------------------

- pkgcore.ebuild.eclass: calculate recursive @PROVIDES in initializer
  to include them in pkgcheck's eclass cache.

- pkgcore.ebuild.eclass: remove 'indirect_eclasses' backwards
  compatibility attribute.

---------------------------
pkgcore 0.12.6 (2021-09-02)
---------------------------

- pkgcore.cache: Invalidate cache entries if they are missing INHERIT
  key, to avoid false positives from pkgcheck's InheritsCheck.

---------------------------
pkgcore 0.12.5 (2021-09-02)
---------------------------

- pkgcore.ebuild.cpv: Explicitly handle invalid revisions.

- pkgcore.ebuild.eclass: Indicate variable types in generated
  documentation.

- Fix unpack to decompress non-archive compressed files into the current
  directory.

- Add support for recursive @PROVIDES eclassdoc tag (replacement
  for @INDIRECT_ECLASSES).

- pkgcore.ebuild.eclass: Include @PROVIDES in generated documentation.

---------------------------
pkgcore 0.12.4 (2021-08-15)
---------------------------

- pkgcore.ebuild.cpv: Fix rejecting valid package names that resemble
  version strings or contain a sequence of multiple hyphens.

---------------------------
pkgcore 0.12.3 (2021-08-14)
---------------------------

- pkgcore.ebuild.repo_objs: Support profile-eapis-banned
  and profile-eapis-deprecated metadata fields (GLEP 82).

---------------------------
pkgcore 0.12.2 (2021-08-04)
---------------------------

- ebd: Start pkg_* phases in a dedicated empty directory required by EAPI 8
  (#313).

- ebd: Fix typo in econf --libdir logic (#318).

- pkgcore.ebuild.repo_objs: Support eapis-testing metadata field (GLEP 82).

- pkgcore.ebuild.atom: Explicitly handle empty string when parsing.

- pkgcore.ebuild.repository: Inject parent repo arches as keywords for provided
  pkgs (#312).

---------------------------
pkgcore 0.12.1 (2021-05-28)
---------------------------

- pkgcore.ebuild.profiles: Provide raw access to make.defaults data for pkgcheck.

- Leverage USE_EXPAND flag ordering from repo to sort output.

---------------------------
pkgcore 0.12.0 (2021-05-22)
---------------------------

- Add initial EAPI 8 support.

- pkgcore.ebuild.formatter: Drop paludis formatter support.

- pkgcore.ebuild.processor: Register ebd cleanup signal handlers on the main
  thread during init to avoid inadvertent issues with 3rd party usage (e.g.
  pkgcore pytest plugin gets autoloaded).

- Rework fetch support to allow custom DISTDIR targets.

- pmaint: Drop mirror subcommand support.

- pshowkw: Move to ``pkgdev showkw``.

- Simplify config-related options by dropping --empty-config in favor of using
  false-valued boolean args to --config. For example, use ``--config no`` or
  ``--config false`` to disable loading the system config where previously
  --empty-config would be used.

---------------------------
pkgcore 0.11.8 (2021-03-27)
---------------------------

- pmaint sync: Fix syncing raw repos.

---------------------------
pkgcore 0.11.7 (2021-03-26)
---------------------------

- pkgcore.ebuild.repository: Rewrite package manifesting support to allow
  partial manifest writes via pkgdev.

- pkgcore.ebuild.portage_conf: Drop PORTAGE_CONFIGROOT and DISTDIR env support.

- pkgcore.ebuild.portage_conf: Handle finding the config directory for prefix
  installs.

- pkgcore.ebuild.portage_conf: Only register existent repos for the config, but
  they're still registered as raw repo_config objects so they can be synced as
  wanted.

- pkgcore.config: Drop unused append_sources param for load_config().

- pkgcore.util.commandline: Drop --new-config/--add-config options.

---------------------------
pkgcore 0.11.6 (2021-03-19)
---------------------------

- pkgcore.pytest: Add support for keeping arches file updated.

- pkgcore.ebuild.domain: Don't configure external repos by default.

- pkgcore.ebuild.repository: Prefer using external repos over configured ones
  for matching repo IDs.

- Use tarball syncer for the gentoo repo by default and drop sqfs entries.

- pkgcore.ebuild.repo_objs: Add 'external' attribute to signify an unconfigured
  repo.

- pmaint: Drop perl-rebuild subcommand.

- pkgcore.ebuild.repo_objs: Support proxied attribute for maintainers.

---------------------------
pkgcore 0.11.5 (2021-03-12)
---------------------------

- pkgcore.ebuild.repo_objs: Add support for parsing upstreams from
  metadata.xml.

- pkgcore.ebuild.repo_objs: Support pulling sign-commits setting from
  metadata/layout.conf.

- pkgcore.ebuild.repository: Support creating repos with custom classes.

- pkgcore.util.commandline: Drop deprecated main() wrapper.

- pkgcore.pytest: Use full version for ebuild file creation.

- pmaint: Drop ``pmaint digest`` support in favor of ``pkgdev manifest``.

---------------------------
pkgcore 0.11.4 (2021-03-05)
---------------------------

- pkgcore.pytest: Add initial pytest plugin for ebuild and git repo fixture
  support.

- pkgcore.util.commandline: Add support for suppressing help output for highly
  pkgcore-specific options users generally shouldn't touch but are needed
  internally.

---------------------------
pkgcore 0.11.3 (2021-02-18)
---------------------------

- Default to tarball-based syncing instead of using sqfs archives in
  fallback config to avoid requiring elevated permissions for CI
  actions.

---------------------------
pkgcore 0.11.2 (2021-01-31)
---------------------------

- Use user cache directory for repo storage when not running on a Gentoo
  system.

---------------------------
pkgcore 0.11.1 (2021-01-29)
---------------------------

- pkgcore.ebuild.domain: Disregard ROOT to avoid infinite loops when using
  find_repo().

---------------------------
pkgcore 0.11.0 (2021-01-27)
---------------------------

- pkgcore.ebuild.conditionals: Add __eq__() and __ne__() support
  for DepSet objects.

- Catch bash stderr output during sourcing for python error
  messages (#277).

- pmaint eclass: Add initial subcommand that supports eclassdoc
  generation.

- pkgcore.ebuild.eclass: Provide support to convert eclassdoc
  objects to rst, manpage, and html formats.

- Inject direct ebuild inherits into metadata cache using the
  'INHERIT' key. This is used by pkgcheck inherit checks.

- Make the base profile node respect profile-formats settings (#293).

- Keep inherit order for inherited eclasses instead of sorting them
  lexically in the metadata cache. The inherit order used by bash
  is useful information for pkgcheck and related tools.

- EbdError: Add die context for non-helper errors to error message.
  This should help give users more context when die() is called
  from ebuilds or eclasses.

- Drop support for python 3.6 and 3.7.

----------------------------
pkgcore 0.10.14 (2020-12-04)
----------------------------

- pkgcore.ebuild.portage_config: Fallback to using a bundled stub
  config and profile on non-Gentoo systems. This should help tools
  that shouldn't require a Gentoo install to function properly
  (e.g. pkgcheck) when installed elsewhere.

- pkgcore.ebuild.domain: Forcibly create new repo_config object for
  add_repo() disregarding cached instances.

- pmaint regen: Add --dir option to support using an external cache
  dir.

- pkgcore.ebuild.digest: Re-raise Manifest parsing errors as
  MetadataExceptions in order for pkgcheck to handle them better.

- pkgcore.util.commandline: Add support for projects that remove
  plugin support functionality.

- pinspect profile: Force profile argument to be non-optional.

- pkgcore.ebuild.eclass: Add initial support for eclass doc format
  parsing.

- pkgcore.ebuild.domain: Raise InitializationError exceptions when
  scanning for repos to aid consumers that try to add external
  repos via add_repo().

- Update default binpkg location to match portage's new default.

----------------------------
pkgcore 0.10.13 (2020-07-05)
----------------------------

- pkgcore.ebuild.domain: Allow license and keyword filters to be
  overridden.

- Add initial arches.desc file parsing support (GLEP 72).

- pkgcore.ebuild.repo_objs: Support testing strings against
  maintainer objects for equality.

----------------------------
pkgcore 0.10.12 (2020-04-15)
----------------------------

- Ignore invalid maintainers in metadata.xml that should be caught by pkgcheck.

- Add support for <stabilize-allarches/> in metadata.xml files.

- Fix eapply_user calls erroring out due to missing patch opts variable.

----------------------------
pkgcore 0.10.11 (2020-01-26)
----------------------------

- Bump required snakeoil version to fix wheel builds.

----------------------------
pkgcore 0.10.10 (2020-01-25)
----------------------------

- pkgcore.ebuild.repo_objs: Fix pulling all text from longdescription
  metadata.xml elements that use embedded XML tags, e.g. <pkg></pkg>.

- pkgcore.ebuild.repository: Add thirdparty mirrors attribute for easy access
  to mirrors defined by an individual repo.

- pkgcore.ebuild.ebuild_src: Add support for flagging redundant SRC_URI
  renames.

---------------------------
pkgcore 0.10.9 (2019-12-20)
---------------------------

- pkgcore.ebuild.repository: Add category_dirs attribute to return the set of
  existing categories from a repo.

- Allow unicode in metadata/layout.conf for repos.

- Ignore inline comments when parsing ebuild inherit lines for directly
  inherited eclasses.

- Log errors in profiles/package.* files instead of raising ProfileError
  exceptions so pkgcheck can properly flag them.

---------------------------
pkgcore 0.10.8 (2019-11-30)
---------------------------

- Add support for validating SLOT values, used by pkgcheck to flag invalid
  SLOTs and pkgs with bad SLOTs will be automasked.

- Add initial profiles/package.deprecated support to flag deprecated packages
  by pkgcheck.

- pclean pkg: Add initial -c/--changed option that allows for scanning the
  related ebuilds for given attribute changes and flagging binpkgs for removal
  if changes exist.

- Add py3.8 support.

---------------------------
pkgcore 0.10.7 (2019-11-04)
---------------------------

- pkgcore.ebuild.eapi: Split archive extension pattern into separate attribute
  for easier use in pkgcheck.

- Fix containment checks for absolute paths against repo objects.

- Fix generating path restricts with relative paths for ebuild repo objects.

---------------------------
pkgcore 0.10.6 (2019-10-05)
---------------------------

- pkgcore.ebuild.repository: Add error_callback parameter for itermatch() to
  allow pkgcheck to redirect metadata exceptions to itself in order to report
  them more easily.

- pkgcore.config.central: Fix recursion error while pickling/unpickling
  CompatConfigManager instances when using a process pool.

---------------------------
pkgcore 0.10.5 (2019-09-24)
---------------------------

- pkgcore.ebuild.eapi: Add deprecated and banned bash commands attributes.

- pkgcore.ebuild.repo_objs: Fix collapsing license groups for
  OverlayedLicenses.

---------------------------
pkgcore 0.10.4 (2019-09-18)
---------------------------

- pkgcore.ebuild.atom: Add no_usedeps property that returns atom object
  stripped of use deps.

- pkgcore.ebuild.cpv: Fix versioned_atom() for unversioned CPV objects.

- pkgcore.repository.prototype: Support returning unversioned matches from
  itermatch().

- pkgcore.ebuild.cpv: Add support for passing (cat, package) for unversioned
  CPVs.

- pkgcore.ebuild.atom: Provide access to all cpv attributes for atom objects.

---------------------------
pkgcore 0.10.3 (2019-09-13)
---------------------------

- Various object pickling fixes for pkgcheck parallelization support.

- pmaint digest: Fix skipping re-manifesting for manifests that are current.

- pkgcore.ebuild.eapi: Split dep keys into their own attribute.

---------------------------
pkgcore 0.10.2 (2019-08-30)
---------------------------

- pkgcore.ebuild.repo_objs: Explicitly add all known repo identifiers as
  aliases. Previously some weren't getting added causing issues when trying to
  use external repos with names matching those of configured repos on the
  system.

- Make explicitly unset EAPI values mean EAPI=0 in accordance with the spec.

---------------------------
pkgcore 0.10.1 (2019-08-26)
---------------------------

- pquery --owns: Fix queries and drop support for comma-separated args.

- pkgcore.ebuild.repo_objs: Use relative paths instead of absolute in logged
  output.

---------------------------
pkgcore 0.10.0 (2019-08-23)
---------------------------

- Dropped dhcpformat/mke2fsformat config format support (and required pyparsing
  dependency).

- GPL2/BSD dual licensing was dropped to BSD as agreed by all contributors.

- pkgcore.ebuild.repo_objs: Add support for processing projects.xml.

- Support PROPERTIES=live as live ebuild indicator.

- The bash ebuild daemon now longer spawns python scripts or uses external
  processes to call back into the python side. Everything is done via IPC
  coordinated by the ebuild processor.

- EAPI 7 support.

- Move the majority of ebuild helpers and some functions into the python side
  including the following: all the do*/new* helpers, keepdir, has_version,
  best_version, unpack, eapply, and eapply_user.

- EAPI specific bash support is loaded before each phase run providing better
  separation between EAPI specific functionality -- newer functions won't even
  exist in scope to be called for ebuilds using older EAPIs.

- pshowkw: Add new utility for displaying/querying package keywords -- an
  analog to eshowkw from gentoolkit.

- Minimum supported python version is now 3.6 (python2 support dropped).

- Add support for transparently using squashfs repo archives.

- Add various tool support for running against ebuilds in unconfigured,
  external repos.

--------------------------
pkgcore 0.9.7 (2017-09-27)
--------------------------

- Use a more dynamic pkgcore._const for wheel-based installs instead of the
  static version used when installing directly to a system. Using a static
  version can't be done because the final paths aren't known until the wheel is
  installed on the target system.

- Fix merging pkgs with non-ascii filenames with python3. Previously pmerge
  would crash when writing the contents file to the vdb.

--------------------------
pkgcore 0.9.6 (2017-09-22)
--------------------------

- Fix building and deploying wheels.

--------------------------
pkgcore 0.9.5 (2017-09-22)
--------------------------

- Fix support for bash-4.4.

- Support -* wildcard for the system packages set in profiles.

- Don't allow external commands to be called during metadata regen.

- pmerge: Don't sort packages in removal mode, just show and unmerge them in
  the order specified.

- Add a tracked attribute for the distfiles used by a package build. This
  installs a file named DISTFILES to the vdb which contains all the distfile
  file names that were needed for the installed package.

- pclean dist: Default to all distfiles if no targets are specified and sort
  output when in pretend mode.

- pmerge: Add initial -o/--onlydeps support similar to portage.

- pmaint digest: Various fixes and enhancements to better handle fetch
  failures, globbed digesting, full repo digesting, and more.

- Fix directory permission issues when using ccache.

- pmerge now supports --list-sets to show the sets pkgcore supports.

- pkgcore.spawn moved to snakeoil.process.spawn.

- Add support for the 'profile-set' profile-formats option in
  metadata/layout.conf.

- Complain if profiles/repo_name is missing for a repository.

- pinspect profile: Add support for specifying a repo with '-r repo' which then
  allows for specifying relative profile paths without the repo prefix.

- pinspect profile: Default to the configured system profile if none is
  selected.

- Fix handling ranges in GLSAs for the related security package set.

- Support for python3.3 was dropped and support for python3.6 was added.

- pmerge: Fix checking for installed packages when passed targets of the form
  'pkg::repo'.

- Support /etc/portage/package.env lines with multiple env file values.

- Support multi-masters instead of singular parents for overlays. This also
  includes merging licenses and categories from all masters for an overlay.

- Drop fallback to default repo for implicit masters. If no masters are
  specified for an overlay in metadata/layout.conf anymore it'll have issues
  depending on packages found in the 'gentoo' repo or whatever master(s) it
  relies on.

--------------------------
pkgcore 0.9.4 (2016-05-29)
--------------------------

- Fix new installs using pip.

--------------------------
pkgcore 0.9.3 (2016-05-28)
--------------------------

- pquery: Add --size, --upgrade, --eapi, and --maintainer-needed options to
  show installed package size or search for packages matching available
  upgrades, a given EAPI, and without any maintainers, respectively.

- pmerge: Add support for reading targets from stdin when *-* is the target
  which supports usage such as **pquery -I 'dev-qt/*:5' | pmerge -1av -**
  instead of forcing command substitution to be used.

- pmaint digest: Skips remanifesting sources for previous distfiles and doesn't
  use Gentoo mirrors for new distfiles by default and adds -f/--force and
  -m/--mirrors options to force remanifesting and force using Gentoo mirrors,
  respectively.

- Add support for PN:slot/subslot and slotted glob targets. This allows for
  targets to pmerge, pquery, and related utilities to accept targets such as
  **dev-qt/*:5** and **boost:0/1.60.0** that signify all Qt 5 libs and all
  packages named *boost* with a slot/subslot of 0/1.60.0, respectively.

- Add initial shell utilities and libraries (bash/zsh), currently available
  tools are *pcd* for changing to a package's directory in any repo
  (vdb/ebuild/binpkg) and *psite* for opening a package's homepage in the
  configured browser using xdg-open.

- EAPI 6 support.

- Additional zsh completion support for most of the remaining tools.

- pclean: New utility currently supporting cleaning distfiles, binpkgs, and
  tmpfiles.

- Officially support python3 (3.3 and up).

- Remove FEATURES=fakeroot support, it hasn't fully worked for years, doesn't
  work with sandbox, and should be replaced with namespace support.

- pmaint regen: Fix cache compatibility issues with egencache, i.e. a cache
  generated by pmaint regen should be able to be used as is by portage without
  it regenerating the cache again.

- pebuild: Ignore repo visibility filters so settings like ACCEPT_KEYWORDS or
  ACCEPT_LICENSE don't matter in terms of package visibility.

- pmerge: Make the --ignore-failures option also ignore pkg_pretend failures.

- pmaint sync: Add git+svn syncer to support mirroring a subversion repository
  using git svn.

- pmaint regen: Add --use-local-desc and --pkg-desc-index options to support
  generating use.local.desc and pkg_desc_index files mostly for portage
  compatibility.

--------------------------
pkgcore 0.9.2 (2015-08-10)
--------------------------

- Add initial zsh completion support; currently most of pinspect, pmaint, and
  pebuild completions should work.

- pmaint digest now ignores various repo visibility filters, this makes it
  possible for regular usage such as generating manifests for ~arch ebuilds on
  a stable system.

- pmerge: pkg_pretend phases are now run after dep resolution similar to
  portage. Previously they were run before displaying the resolved dep tree.

- Calling die() now works as expected from within subshells.

- Drop deprecated support for /etc/make.profile, only /etc/portage/make.profile
  is supported now when using portage config files.

- A commandline option '--config' allows the user to override the location of
  config files. If set to a file location it assumes it's a pkgcore config
  file; otherwise, if it's set to a directory it assumes its a portage config
  directory (e.g. /etc/portage).

- pkgcore.config: The location parameter to load_config(), if set, can now
  either point to an alternative pkgcore config file or portage config
  directory. Previously it only supported an alternative portage config
  directory's parent as an argument. External usage should be fixed to use the
  full path to the config directory, e.g. /etc/portage instead of only /etc.

- Use correct EPREFIX and EROOT settings. This fixes non-prefix builds when ROOT
  is non-null.

--------------------------
pkgcore 0.9.1 (2015-06-28)
--------------------------

- Fix installing via pip by using setuptools when available; however, note that
  snakeoil must still be installed manually first since pkgcore's setup.py
  script currently depends on snakeoil modules.

- Improve support for syncing repos defined in repos.conf, add syncers
  supported by pkgcore should work as expected.

- Support for PORTDIR and PORTDIR_OVERLAY in make.conf has been dropped, only
  repos.conf is supported.

- Drop deprecated support for /etc/make.globals, only make.globals provided by
  pkgcore is used now.

- Add support for /etc/portage/make.conf as a directory. All regular, nonhidden
  files under it will be parsed in alphabetical order.

- Drop deprecated support for /etc/make.conf, only /etc/portage/make.conf is
  used now.


------------------------
pkgcore 0.9 (2015-04-01)
------------------------

Features
========

- Hardlinks are now preserved during merging and when creating binpkgs.

- Add pmerge support for globbed targets, this means that commands such as
  **pmerge "*"** or slightly more sane **pmerge "dev-python/*::repo"** will
  work. Note that this usage is apt to run into blockers and other resolver
  issues, but it can be handy in certain cases.

- Drop pmerge support for -s/--set in favor of @pkgset syntax.

- Add pmerge support for -b/--buildpkg and change --with-built-depends to
  --with-bdeps to match emerge.

- Nearly complete EAPI=5 support just missing subslot rebuilds.

- Add support for pebuild to run against a given ebuild file target from a
  configured repo. This is the standard workflow when using `ebuild` from
  portage.

- Add unmasks, iuse_effective, bashrcs, keywords, accept_keywords, pkg_use,
  masked_use, stable_masked_use, forced_use, and stable_forced_use as `pinspect
  profile` subcommands. Also, note that 'profile' is now used instead of
  'profiles'.

- Add support for FEATURES=protect-owned (see make.conf man page for details).

- Add `pinspect query get_profiles` support.

- Add support for COLLISION_IGNORE and UNINSTALL_IGNORE variables (see
  make.conf man page for details).

- Add support for FEATURES=test-fail-continue. This allows the remaining
  phases after src_test to continue executing if the test phase fails.

- Add eqawarn support.

- Add support for profile-defined PROFILE_ONLY_VARIABLES to prevent critical
  variables from being changed by the user in make.conf or the env.

- Move to using portage's keepdir file naming scheme (.keep_CAT_PN-SLOT)
  while still supporting pkgs using the previous ".keep" method.

- Support the portage-2 profile format.

- Update pmerge's portage-like output to more closely approximate current
  portage releases.

- Add pmerge options -O and -n to match --nodeps and --noreplace similar
  to portage.

- Add profile-based package.accept_keywords, package.keywords, and
  package.unmask support and force the profile base to be loaded by default so
  related settings in the profile root dir are respected.

Fixes
=====

- Fix granular license filtering support via /etc/portage/package.license.

- Don't localize file system paths by resolving symlinks to provide a
  consistent view of merged files between pmerge output and the vdb.

- Fix installing symlinks via doins for >= EAPI-4.

- Define SLOT and USE for pkg_pretend (mirroring portage) so checking for
  enabled use flags during pkg_pretend works as expected.

- Run pkg_nofetch phase when any files in SRC_URI fail to be fetched.

- Apply use flags from make.defaults before package.use in profiles.

API Changes
===========

- Deprecated pkgcore.chksum compatibility shim removed.

- .eapi attribute on packages is now mostly unsupported; should instead use
  .eapi_obj instead (an alias will be left in place for that long term).

- format_magic attribute was dropped from ebuild repositories; shouldn't
  have been used (was always a hack).

Other
=====

- Add tox config to allow running the testsuite across all supported python
  versions.

- Handle SIGINT signals better with regards to spawned processes that might
  alter them. Now hitting Ctrl-C once should force pkgcore to exit as expected
  instead of having to hit Ctrl-C multiple times at certain points during
  package builds such as when a spawned python process is running and captures
  the signal instead of relaying it to its children.

- Old virtuals support deprecated by GLEP 37 has been dropped.

- No longer depend on config files from portage. Global config files are now
  stored in /usr/share/pkgcore/config and bash-related functionality is stored
  in /usr/lib/pkgcore instead of each pkgcore module's namespace.

- Throw warnings for EAPI support in development instead of erroring out.

- Define ${T} for pkg_pretend phase, allows things like check-reqs for disk
  tempspace to work properly.

- Support for multiple slots in a single atom dependency was removed;
  never made it into a mainline EAPI and isn't useful these days.

- Pkgcore now parses EAPI from the ebuild itself, rather than from the
  metadata calculated value.


--------------------------
pkgcore 0.8.6 (2012-10-29)
--------------------------

- Fix false positive test failure under py3k related to /etc/passwd
  encoding (gentoo bug 439800).

- Better error messages for config errors.


--------------------------
pkgcore 0.8.5 (2012-10-18)
--------------------------

- pkgcore now matches the new PMS rules on package naming (specifically
  that the last component can't be a version at all, period).  Also
  tightened up some stupidly horrible allowed names- stuff like diff-mode-
  for a package name (gentoo bug #438370).

- pkgcore no longer supports the old form cvs version component; for
  example, diffball-cvs.1.0 (cvs version of 1.0 for diffball).  This has
  long since been deprecated- basically since day 1 of cvs.  It's been
  basically six years, no vdb usage should exist anymore, thus dropping
  support for it.

- Fixed test sporadic test failure- false positive code quality check.
  Gentoo bug 437216.

- Fixed doc generation for py3k.


--------------------------
pkgcore 0.8.4 (2012-10-04)
--------------------------

- Fix bad function reference in eapi3 guts.


--------------------------
pkgcore 0.8.3 (2012-10-04)
--------------------------

- Fixed bug where default phases weren't guaranteed to be ran.


--------------------------
pkgcore 0.8.2 (2012-10-01)
--------------------------

- Fixed pmaint exception for when eclass preloading was enabled.


--------------------------
pkgcore 0.8.1 (2012-09-29)
--------------------------

- Pkgcore now requires snakeoil 0.5.1.

- The cache format 'md5-cache' is now supported (this is what gentoo-x86
  switched to, and what chromeos uses).

- core environment saving functionality was sped up by ~10x.  Basically
  every package will see a gain; simple ones like bsdiff, on my hardware
  went from ~5.2s to 1.5s; diffball from ~12.4 to ~9.2; hell, even
  git (with binpkgs turned off) dropped from 28.5s to 21.1s.
  This improves both --attr environment, and general functionality;
  regen however shouldn't be any faster (already avoided these pathways).

- filter-env gained a --print-funcs option.  Additionally, the underlying
  core has been enhanced so that analysis within a function block is
  possible.

- pquery --attr environment now can work for raw ebuilds, rather than
  just built ebuilds.

- pquery --no-filter was added; this gives you the configured
  (USE rendered) view of a package, just without any visibility
  or license filtering applied.

- Errant newlines in pquery --attr \*depends -v output were removed.

- pquery --repo gentoo no longer implies/forces --raw.  Same goes
  for all other places that take repo arguments.
  Now, pquery --repo <some-repo> must be within the specified domain
  unless --raw is forced.

- All pkgcore internal functions now are prefixed with __; ebuilds
  and eclasses should never touch them.

- For performance debugging of EBD, PKGCORE_PERF_DEBUG=1 was added.

- Defined phases is now trusted in full, and used to control exactly
  what phases are actually ran.  This in conjunction w/ some relaxation
  of a few protections (namely, if pkgcore just generated the env dump,
  and we know it's from our version/machinery, then we can directly
  source that dump rather than doing protective scrubbing).  End result
  is that for build -> binpkg -> install, for example bsdiff went from
  4.9s to 2.1s; diffball went from ~12.5s to ~9.8s.  Gain primarily
  is for either huge environments, or small pkgs.

- Minor round of metadata regen optimization; 18-20% faster now.

- Heavy environment cleanup; pkgcore now generally doesn't expose
  any real functionality to ebuilds/eclasses that could be accidentally
  relied upon (all of it is prefixed with pkgcore\_, making it obvious
  they shouldn't be using it).

- Fix issue #31; empty GENTOO_MIRRORS breaks portage conf support.


------------------------
pkgcore 0.8 (2012-08-04)
------------------------

- Fix fetch support broken by gentoo's recent enabling of whirlpool
  checksum.

- Python 2.4 support was dropped.

- Fix a longstanding potential bug in spawn's fd reassignment;
  if fed {2:3, 3:2, 4:6}, dependent on python dict ordering, it
  was possible for it to inadvertantly stomp fd 4 during the
  final reassignment.  Haven't seen any signs it's occurred in the
  wild, but the potential is there, thus fixed.

- Gentoo's unpacker eclass is sensitive to the return code of
  assert; this is outside of pms rules, but we've matched portage
  behaviour to keep things working

- Fixed pinspect portageq envvar support.

- Added `pconfig world` for world file manipulation.

- Heavy doc fixups, including fixing the man pages to actually be
  readable.  New man page for pmerge added.

- Fix py3k incompatibility in pmerge -N .

- prefix branch was merged.  This fleshes out the majority of prefix
  support; extended-versions currently aren't supported however.

- pkgcore now forces parallelization for tbz2 generation if pbzip2
  is installed.

- Python stdlib's BZ2File doesn't handle multiple streams in a bz2
  file correctly- we work around this via always forcing bzip2 -dc
  unless the python version is 3.3 or later.


----------------------------
pkgcore 0.7.7.8 (2011-01-26)
----------------------------

- pkgcore's merger now will preserve any hardlinks specified in the
  merge set.  Merges straight from binpkgs don't currently preserve
  hardlinks.

- added hardlink awareness to splitdebug and stripping.  For pkgs
  that install hardlinks (git for example), this fixes double stripping
  and complaints output during merging for trying to splitdebug it.
  Bit faster in addition since for git, it cuts the splitdebug down
  from 110 to 7 or so.

- Fix incompatibilities in pinspect portageq api that eselect uses.
  Eselect will be updated to use better api's moving forward, but
  till then restore support.

- pinspect portageq and pinspect query envvar now return space delimited
  string values if the queried value was a list.

- Fix bug where use dep forced changes to use state weren't honored
  at the build level.

- Fix fairly serious bug where immutable use flags (arch for example),
  wasn't being enforced for pkg dependency calculations.


----------------------------
pkgcore 0.7.7.7 (2011-01-24)
----------------------------

- pkgcore resolver now understand weak blockers.  This fixes a long
  standing issue where portage/paludis would allow a transaction that
  pkgcore would refuse (at the time of pkgcore's creation, weak/strong
  didn't exist- just strong).

- work around eselect incompatibility for root not always being specified
  to `pinspect portageq get_repositories`.

- Better error reporting for mistakes in incremental vars in configuration.


----------------------------
pkgcore 0.7.7.6 (2011-01-16)
----------------------------

- fix bug where REQUIRED_USE wasn't being stored during metadata
  regeneration.  Thanks to marienz for reporting it.

- FEATURES=compressdebug support was added.  This enables splitdebug
  to compress the generate debug files; this can easily reduce the footprint
  from 20GB to ~8GB on an average system.

- no longer complain about incorrect profiles/categories files.  PMS,
  and people who hate QA suck.


----------------------------
pkgcore 0.7.7.5 (2011-12-26)
----------------------------

- pkgcore no longer requires a manifest to exist if the repository uses
  thin-manifests, and there are no distfiles for a pkg.

- removed support for FEATURES=allow-missing-checksums.  Use repository
  metadata/layout.conf use-manifest setting instead.

- complain about incorrect profiles/categories files.

- fix bug in masters handling where eclass lookup order was reversed.

- pinspect subcommand digests was added; this is used for scanning for
  broken manifest/digests in a repository.

- PORTAGE_LOGDIR is supported again.

- pkgcore no longer intermixes python/bash output incorrectly when stdout
  or stderr or the same fd: pmerge -Du @system &> log for example.

- issue #7; add framework for parallelized trigger execution.  Currently
  only splitdebug/stripping uses it, but it has a sizable gain for pkgs
  with many binaries.

- pmaint regen --disable-eclass-preloading is now
  pmaint regen --disable-eclass-caching.

- ctrl-c'ing pmaint regen hang bug is now fixed.

- fix a bug in pmaint regen and friends where if the requested repository
  isn't found, the last examined is used.  Additionally, restore ability
  to specify a repository by location.

- all operation api's now are chained exceptions deriving from
  pkgcore.operations.OperationError; for CLI users, this means we
  display a traceback far less often now.

- pkgcore configuration subsystem now uses chained exceptions.  In
  accessing it, you'll get a ConfigurationError exception (or derivative)
  for any config data errors, or the appropriate exception if you use the
  subsystem incorrectly.  In the process, reporting on errors to the commandline
  is now augmented.


----------------------------
pkgcore 0.7.7.4 (2011-12-14)
----------------------------

- pkgcore now requires snakeoil 0.4.6 and higher.

- `pinspect profiles` no longer requires parsing the system configuration.

- COLUMNS now is always 0 or higher to make perl (gentoo bug 394091)
  play nice.

- FEATURES=distcc-pump support was added; issue #21.


----------------------------
pkgcore 0.7.7.3 (2011-12-08)
----------------------------

- fixed merging error for gconf files named %gconf, and introduced
  better error messages for those sort of failures.


----------------------------
pkgcore 0.7.7.2 (2011-12-07)
----------------------------

- `pquery --attr source_repository --vdb` now correctly returns the
  originating repository.

- pmerge --source-only was added; this disables all binpkg repositories
  from being used for the resolution; binpkg building however still will
  occur if the feature is enabled.

- fixed potential for eclass preloading to use the incorrect repo source.
  This could only be triggered by actual API usage, not from commandline
  usage.

- ebuild package instances now have an officially supported .inherited attribute
  for finding out the eclasses used by a pkg.  In addition, this attribute
  is now installed into the vdb repository, and binpkgs.

- pkgcore no longer adds REQUIRED_USE to vdb nor binpkg; it's a pointless
  metadata key, plus we used to corrupt it.

- fixed bug where portdir write cache wouldn't be created, nor used.
  Wasn't seen primarily due to regen being fast enough it's not a huge
  issue.

- fixed addition stacking issue w/ eclass defined REQUIRED_USE resulting
  in corrupted IUSE.

- fixed long standing race that could occur during pmaint regen leading
  to an ebuild failing to be regenerated.

- added protection and QA scanning for bad IFS/shopt/set manipulation
  by user code.


----------------------------
pkgcore 0.7.7.1 (2011-12-02)
----------------------------

- Fix eclass metadata var (IUSE for example) stacking in metadata
  phases.

- Fix has invocations in ebuild helpers


--------------------------
pkgcore 0.7.7 (2011-12-02)
--------------------------

- pmaint regen optimizations.  This is now >5x faster than 0.7.6,
  and ~3x faster than 0.7.2 (0.7.3 introduced a regression).

- restore pmaint sync support for unsynced repositories.

- support lookup of a repo by its name, rather than just by path.
  This affects pquery --repo, pmaint sync, pmaint copy, pinspect, etc.

- --debug now again enables full traceback output for config failures.


----------------------------
pkgcore 0.7.6.1 (2011-12-01)
----------------------------

- fix portage_config generation bug in 0.7.6; in the process, forced
  overlay's eclass stacking onto PORTDIR is no longer done by default.


--------------------------
pkgcore 0.7.6 (2011-11-30)
--------------------------

- pplugincache now removes old caches when ran.

- pkgcore now honors layout.conf masters for eclass stacking.

- pplugincache now forces an update, regardless of mtimes involved.

- pkgcore internal configuration was rewritten to be stricter, while
  allowing far more overriding.  In general, it should now do what
  you would expect.  Exact details, see the git logs.

- plugin cache format is now v3; this improves performance primarily.


--------------------------
pkgcore 0.7.5 (2011-11-07)
--------------------------

- pkgcore now extends masking rules to binpkg repositories; in addition,
  it now honors 'masters' for masking.  This means repositories that
  try to suppress an inherited mask that affects that repo, can now
  do so.

- fix bug- export ROOT to pkg_pretend invocations.

- pkgcore no longer export PWORKDIR; this was in use via extremely old
  libtool versions as a way to do QA; no longer needed.

- match multirepo portage behaviour; specifically, no longer force overlay
  version shadowing.


--------------------------
pkgcore 0.7.4 (2011-10-27)
--------------------------

- fix userprofile stacking for /etc/portage/profile; this fixes a traceback.


--------------------------
pkgcore 0.7.3 (2011-10-26)
--------------------------

- speed up directory walking; varies, but ~25% faster.

- pkgcore no longer allows comments in profiles/categories.

- pkgcore now allows profile package.mask and friends as directories for user
  configuration, and within repositories that set profile-formats = portage-1
  in their layout.conf.

- pquery --expr was removed.  Open to re-adding it, but in a maintainable
  form that has testing, and is usable elsewhere.

- pquery now if given no restrictions, defaults to --all.

- pquery argument parsing was rewritten; ordering issues for --config
  were fixed, error messages improved, and general cleanup.

- fix traceback that occurs when unmerging a pkg, but tempspace needs
  to be created.

- initial layout.conf support; thin-manifests, use-manifests, and
  controllable hashes.


--------------------------
pkgcore 0.7.2 (2011-09-27)
--------------------------

- bug fixes; fix to pebuild so it works again, bugs spotted by pyflakes,
  etc.  Basically codebase cleanup.

- experimental support added for generating Manifests via pmaint digest.

- pkgcore no longer supports manifest version1; nothing else supports
  it now, it's no longer in use, thus the removal.

- new pmaint 'mirror' command.  This is used for pulling down
  all distfiles that could be required for a specific package.

- operations proxy no longer triggers infinite recursion.


--------------------------
pkgcore 0.7.1 (2011-09-03)
--------------------------

- add TIMESTAMP header to binpkg Packages cache.

- mangle and add compatibility to source_repository handling to make
  it play nice w/ past transgressions, and generate in a form portage
  will like.

- fix traceback in binpkg installation

- fix pclone_cache hang

- suppress spurious slot shadowing test failure; occurs dependant on
  GC behaviour, the complaint however doesn't matter (it false-negatives
  on a mock object used for tests).


------------------------
pkgcore 0.7 (2011-09-02)
------------------------

- pmaint regen now supports regenerating binary and install repository
  caches.

- pkgcore now tracks and records the originating/source repository
  when installing to the vdb.

- new pkg attribute; source_repository.  This tracks where a package
  originated from- primarily useful for binpkgs and vdb.
  pquery --attr source_repository is how to access it from the CLI.

- pkg_config can now be invoked via:
  pconfig package <target>

- splitdebug no longer runs if the pkg has been split already.

- arbitrary exceptions during merging/unmerging no longer stop the
  merge/unmerge; a traceback is displayed instead.

- added initial profile inspection tool; pinspect profiles.

- pmaint copy arguments have changed; check the help, short version,
  it's now sane.

- pkgcore now lives at googlecode; http://pkgcore.googlecode.com/

- large scale conversion of internals to argparse.  Saner parsing namely,
  although it's still a work in progress to make it pretty.

- man pages and docs in general have been converted to sphinx.  Definite
  improvement already, but more to come.

- pkgcore observer api's were heavily gutted and split into observer and
  outputter.  This should enable easier UX integration, while enabling
  our next step towards parallelization.


--------------------------
pkgcore 0.6.6 (2011-07-11)
--------------------------

- make use/useq/usev extremely obnoxious towards offending devs who use them
  in global scope when they're not supposed to.  Pretty much, I'm tired of
  pkgcore being broken for being PMS compliant; as such I'm now pointing
  users loud and clear at the offenders.

- fix traceback in user profile support (/etc/portage/profiles).


--------------------------
pkgcore 0.6.5 (2011-06-22)
--------------------------

- Log an error, rather than throwing an exception when binpkg cache cannot
  be updated.  Needs refinement long term, but for average users, this is
  preferable.

- loosen up pebuild a bit; choose the max version if slot/repo are all the
  same.  This allows pebuild dev-util/nano to choose 2.3.1 for example.

- tighten up econf implementation; ctarget/cbuild are now forced as early
  arguments to configure to work around some misbehaviours in configure
  scripts (broken scripts, but so it goes).

- tighten up ebuild environments variable handling- had a bleed through
  of variable 'x' that was breaking mesa builds.

- yet another src_install fix for EAPI=4; this time ensuring the default
  function is available.

- we now run bashrcs (profile and user) every phase to match portage
  behaviour.  If folks desire it, a patch making that optional would be
  welcome.

- add support for /etc/portage/package.env and /etc/portage/env/.  Note
  that we only allow settings there to affect the bash environment- trying
  to adjust FEATURES from those files isn't on the intended support list.

- use ${LIBDIR_${ABI}} for ccache/distcc pathways; gentoo bug 355283.

- profile interpretation of make.defaults now has access to variables
  defined by its parents, per PMS.


--------------------------
pkgcore 0.6.4 (2011-06-05)
--------------------------

- intercept and suppress exceptions from triggers unless the trigger
  explicitly disables it.

- work around libmagic python bindings sucking and not always being
  able to be used.

- fix 'default' support for src_install for EAPI=4.


--------------------------
pkgcore 0.6.3 (2011-05-30)
--------------------------

- support for /etc/portage/make.profile; Please Do Not Use it, while
  pkgcore is forced to support it, usage of it breaks most tools and is
  bluntly lock-in (no reason to move it- it's the same, been in the same
  place for a decade now).  Duly warned.

- misc env/bug fixes for EMERGE_FROM to ensure compatibility.

- deploy eselect support via pinspect portageq

- added man page for pinspect

- added pmaint env-update

- expose /usr/local/* through PATH for ebuilds.


--------------------------
pkgcore 0.6.2 (2011-05-27)
--------------------------

- for EAPI<4, expose MERGE_TYPE info via EMERGE_FROM; do this for compatibility
  with non-spec compliant ebuilds, and eclasses like linux-mod.  This restores
  in particular, binpkg support for kernel packages.  Thanks to Brian De Wolf
  for info leading to tracking this down.

- add support for stacking /etc/portage/make.conf on top of /etc/make.conf.

- add incrementalism between make.globals and make.conf to match changes
  in portage configuration parsing.  This fixes the common "I tried pkgcore
  and everything was license masked".  Breakage there owes to portage
  changing make.globals; can't do much about it unfortunately.  Thanks to
  Brian De Wolf for info leading to tracking this down.

- prefer 0755 permissions for binpkg package dir.

- pinspect pkgset learned --all option, to display all pkgsets it knows.


--------------------------
pkgcore 0.6.1 (2011-05-27)
--------------------------

- fix for "or_node.blocks" AttributeError, and related resolution
  miscalculations.

- fix exit code return for ebuild helpers throwing warnings for <EAPI4

- fix typo in FEATURES=buildsyspkg, and FEATURES=buildpkg

- check to ensure pkgdir exists; if possible, create it, else turn off binpkg
  features.


------------------------
pkgcore 0.6 (2011-04-24)
------------------------

- Due to crazy work hours and moves, this release is fairly large, and frankly
  repeatedly delayed.  Future ones will be far more fine grained moving forward.

- Fix python2.7 incompatiblity in pkgcore.ebuild.misc

- It's suggested that folks use bash 4.1, primarily for regen
  speed reasons- it is not required however.

- bash spawning now enforce --norc and --noprofile in full.

- RESTRICT is now properly use evaluated.

- pkgcore.restrictions.values.ContainmentMatch is deprecated in favor of
  ContainmentMatch2.  Update your code- by pkgcore 0.7, ContainmentMatch
  will become ContainmentMatch2, and a shim will be left in place.

- introduction of EAPI objects (pkgcore.ebuild.eapi) for controlling/defining
  new eapi's, capabilities, etc.

- pmaint regen is now cumulatively ~23x faster then the previous release.
  This is via restoration of original metadata regeneration speeds, and
  via enabling an eclass preloading optimization.  No impact on metadata-
  just far faster regeneration.

- Roughly a 15x speedup in general metadata regeneration; basically rework
  a fix that was added to to 0.5.11 (dealing with portage induced
  breakage in env loadup from their declare usage).

- filter-env regex backend now uses python's re always; previously
  if the extension was active it would use posix regex.

  This resolves occasional odd failures when running native filter-env.

- fix a truncation error in suffix version parsing resulting in
  _p2010081516093 being less than _p2009072801401 .

- pkgcore.ebuild.restricts now contains some generally useful
  building block restrictions for any api consumers

- full rewrite of EAPI helpers adding better error info, saner code,
  double checked against PMS and portage/paludis to ensure no oddities.

- fix to buildpkg/pristine-binpkg saving.  If you're looking for
  something to contribute to pkgcore wise, tests for this would be
  appreciated.

- write support for DEFINED_PHASES.

- bashrc hooks now run from ${S} or ${WORKDIR}, depending on
  PMS rules for that phase.

- match the other PM's for econf; update ${WORKDIR} instances of
  config.{sub,guess} from /usr/share/gnuconfig.

- added protection against bad environment dumps from other PMs for T
  during env restoration.

- removed RESTRICT=autoconfig support.

- fix compatibility regression introduced in file-5.05 involving MAGIC_NONE.

- handle keyboard interrupts better during compilation; no longer display
  die tracebacks if the user intentionally stopped the compilation.

- duplicate a portage workaround for emacs ebuild; specifically don't
  regenerate infodir if the ebuild placed a .keepinfodir in the directory.
  gentoo bug #257260.

- add workaround to disable unzip during unpack going interactive during
  a failure; gentoo bug #336285.

- fixed traceback during displaying a summary for 'pinspect eapi_usage'

- add EAPI limitation to all portageq invocations, and support USE dep
  usage with has_version and friends.

- handle portage's new interpretation of the sync retries variable for portage
  configuration.

- pinspect distfiles_usage was added; this is primarily useful for getting
  a repository level view of what the distfiles requirements are, what takes
  what percentile of unique space, etc.

- FEATURES=allow-missing-manifests ; does exactly as it sounds, not advised to
  use unless you know what you're doing.

- ospkg's fork of pkgcore has been folded in; FEATURES=save-deb is the primary
  addition.

- extended atom syntax now allows '*' to be used w/in a string- for example
  dev-\*kde, \*dev-\*k\*de\*, etc.  This syntax is usable in user configs, and
  from the commandline.

- new FEATURES=fixlafiles is on by default; basically folds
  dev-util/lafilefixer functionality directly into the merger.
  Note this version drops comments- it's about a 66% reduction in .la system
  filespace requirements via doing so.

- triggers base class now carries a ConfigHint to provide a typename.  If
  a specific trigger cannot be specified by configuration directly, set
  pkgcore_config_type = None to disable the hint removing it from being
  directly configurable.

  For users: this means basically all triggers are now directly usable in
  configuration.

- object inspection for configuration can now handle object.__init__ for
  config 'class' targets; no need to define an intermediate function.

- ConfigHints can now specify authorative=True to disable all introspection.
  Mainly usedful for cpy objects, although useful if you want to limit what
  the introspection exposes.

- api's for installing pkgs has changed; now to install a pkg to a domain,
  you invoke domain.(install|uininstall|remove)_pkg.  To just modify a repo,
  access its operations for the appropriate operation.

- pkgcore.interfaces was moved to pkgcore.operations

- pkgcore.package.base derived objects no longer default to _get_attr dict
  lookup- if you want it, set __getattr__ = dynamic_attr_dict.

- USE is now locked an intersection of the pkgs IUSE, with forced flags
  (things like arch, userland, prefix, etc) added on.  Mild speed up from
  dealing with a reduced set, more importantly portage switched to controlled
  USE here, so we can force it finally.

- USE collapsing now should match portage behaviour.  Essentially now,
  pkg IUSE + profile overrides + make.conf overrides + user config package.use
  overrides.  Previous behaviour didn't get edge cases correct.

- USE_EXPAND default iuse is now fully overridden if the target USE_EXPAND
  groupping is defined in configuration.  Mostly relevant for qemu-kvm.

- data_source.get_(text|bytes)_fileobj invocations now require writable=True
  if you wish to mutate the data source.  Via making the intention explicit,
  consumers will get just what they need- a 3x speed up for
  pquery --attr environment is from that internal optimization alone.

- pkgcore.fs.fsFile.data_source is deprecated; will be removed in the next
  major version, use .data instead.

- pkgcore.interfaces.data_source moved to snakeoil.data_source.

- pkgcore.chksum moved to snakeoil.chksum.  A compatibility shim was left in
  for pkgcore-checks, which will be removed in 0.7 of pkgcore.

- pkgcore ticket #172; rely on snakeoil.osutils.access to paper over differing
  os.access behaviours for certain broken userlands (SunOS primarily).


-----------------------------
pkgcore 0.5.11.8 (2010-07-17)
-----------------------------

- ticket #221; add --color=(n|y) support

- pmaint perl_rebuild was added; right now it just identifies what needs
  rebuilding on perl upgrades, but down the line it'll do the rebuilds as
  needed.

- pkgcore now ignores ebuild postrm exit status- it logs failures, but there
  isn't really anything that can be done at that stage (everything is already
  unmerged after all).

- fixed pkgcore.fs.livefs.iter_scan to support a path pointing to a
  nondirectory.

- force all sourcing to stderr; this protects against idiocy like the
  python eclass trying to write to stdout in color during sourcing.

- commandline.OptionParser now does a shallow copy of all items in
  standard_options_list; this protects against class/instance level cycles
  inherent in optparse.OptionParser's design.


-----------------------------
pkgcore 0.5.11.7 (2010-06-20)
-----------------------------

- use_enable/use_with; make use_enable/use_with 3rd arg form match pms in eapi4,
  match long standing portage behaviour for eapi's 0 through 3.

- when combining repository and slot restrictions in an atom, repository is now
  always prefixed with ::, not intermixed.  sys-apps/portage:0::gentoo for
  example specifies slotting 0, repository gentoo.

- fixed a bug in installed pkgs virtual cache staleness detection- this
  accounted for a surprisingly hefty ~25% for simple pquery invocations.

- fix typo in env protection code- load the scrubbed env, not the raw source.


-----------------------------
pkgcore 0.5.11.6 (2010-05-21)
-----------------------------

- add a bit of a hack to tty detection tests; PlainTextFormatter is valid for
  broken terminfo entries.

- fix support for unpacking of xz tarballs.


-----------------------------
pkgcore 0.5.11.5 (2010-04-22)
-----------------------------

- fix yet *another* fucking distutils bit of idiocy.  Piece Of Shit.


-----------------------------
pkgcore 0.5.11.4 (2010-04-21)
-----------------------------

- fix py3k regression when trying to hash a PackageRestriction.

- drop CDEPEND tracking (unused, hold over from '04 days), and
  newdepend (same era).  Neither are used in >=EAPI0 ; if your
  ebuild breaks, rebase the ebuild to a valid EAPI.


-----------------------------
pkgcore 0.5.11.3 (2010-03-22)
-----------------------------

- force all einfo/elog/ewarn style bits to stderr.

- add path attribute to ebuild derived pkg instances; not a guaranteed
  part of the api yet, but accessible via pquery --attr path


-----------------------------
pkgcore 0.5.11.2 (2010-03-16)
-----------------------------

- silence spurious grep QA warnings during metadata sourcing.


-----------------------------
pkgcore 0.5.11.1 (2010-03-15)
-----------------------------

- fix a major release bug; ebuild-env-utils.sh wasn't packaged in the
  released 0.5.11, this version adds the missing file.

- more declare related fixups; this one a regression from 0.5.10- in
  sourcing /etc/profile.env, its contents weren't being preserved
  fully due to declare.

- add missing eapi3 phase support- basically just reuses eapi2's since
  the only changes are environmental.


---------------------------
pkgcore 0.5.11 (2010-03-14)
---------------------------

- took me a full night of debugging, but traced down yet another portage
  incompatibility introduced.  gentoo bug 303369; if you've been seeing
  issues where portage merged ebuild envs aren't reused in pkgcore, this
  is now fixed.  Env handling in general was heavily rewritten to be as
  robust as possible and protect against any further breakages from portage.

- env processing is a bit faster now- uses egrep where possible, falling
  back to bash regex where not.

- shell scripts now are tabs based rather than spaces.

- FEATURES=splitdebug works once again.

- It's strongly suggested that you run >snakeoil-0.3.6.1 due to fixes
  in extension building- specifically forcing -fno-strict-aliasing back
  into cflags since python is invalidly dropping them out.

  In addition, if you're running pkgcore on a py3k machine, installation
  now is parallelized for 2to3 conversion- should be a fair bit faster.

- rename support for env var CONFIG_ROOT to PORTAGE_CONFIGROOT; seems
  that changed in portage at some point.  This should fully restore
  crossdev support.


---------------------------
pkgcore 0.5.10 (2010-02-07)
---------------------------

- ticket 235; CBUILD/CTARGET values were being stomped w/ CHOST.

- EAPI=3 support; pkgcore already preserved mtimes at the second level,
  remaining bits were added for full EAPI3 support.

  Pkgcore doesn't currently fully PREFIX offset merges, but that will be
  added in the next release or two most likely.

- EBUILD_PHASE was set to setup-binpkg for pkg_setup phase w/ binpkgs-
  ebuilds expected setup however, thus EBUILD_PHASE is now set to setup
  always for pkg_setup phase.

- fixup env filtering- backslash escaping wasn't needed in the patterns
  resulting in failed matches.  Mostly protective cleanup.

- tweak cache backend to not stamp cache entries where mtime is no longer
  external w/ an mtime of '-1'.  Didn't hurt anything but was a pointless op.

- fix the cpy incremental_expansion implementation; not sure how it slipped
  in being slower then native python, but the cpy version is now 60% faster
  than the native equivalent.
  Additionally, this extension is now disabled under py2.4 since it makes
  heavy use of PySet apis.

- ticket 234; handle refs properly in dhcpformat/mke2fsformat.

- pkgcore atom objects blocks_temp_ignorable data is now stored in
  blocks_strongly; the old attr is aliased, although will be removed.

- pkgcore now supports revisions of arbitrary length (previously was <31 bits).


--------------------------
pkgcore 0.5.9 (2010-01-08)
--------------------------

- this release of pkgcore requires snakeoil >=0.3.6

- expand repository api slightly adding has_match; this is intended
  as a simple boolean check if a repo has it.  It should *only* be
  used for containment- if you need the results don't test then itermatch,
  just itermatch.

- add cpy implementation of PackageRestriction.match

- for package.provided repositories, short circuit their itermatch/match
  if there aren't any results possible.

- re-enable cpython implementation of DepSet parsing for eapi2- roughly
  a 31% speedup for current gentoo-x86 repository dependency parsing.

- performance improvements to pquery --attr alldepends; specifically
  depset.stringify_boolean is now 20% faster.

- performance improvements to pquery --attr alldepends -v


--------------------------
pkgcore 0.5.8 (2009-12-27)
--------------------------

- >snakeoil-0.3.4 is required for this release.

- key is reused as cpvstr for memory savings where possible in cpv
  extension objects.

- cpv extension objects now intern package, category, and key for
  memory reduction reasons.

- various slot fixups to reduce memory usage and potential corner case
  bugs.

- fix the scenario where there is one repo returned from the domain for
  pmerge... crappy bug feedback on that one lead to it slipping by.


--------------------------
pkgcore 0.5.7 (2009-12-22)
--------------------------

- added pinspect script; used for basic reporting of metadata usage,
  and inspection of pkgsets.  Bit simple, but will be expanded down the line.

- filter-env is now installed into PATH; cli api isn't considered stable,
  but it should be useful for folks playing w/ bash environments or doing
  ebuild inspection.

- correct a tb in pmerge when the user configuration is strictly a single
  source repository.  Semi rare, but can occur.

- correct a tb when throwing a missing file error for specifying package.*
  settings directly to domain.

- correct a tb in profiles expansion code of USE_EXPAND and USE_EXPAND_HIDDEN
  when they're completely undefined in the profile stack.  Rare, but if a
  user is building a custom profile stack from the ground up, it's possible
  to hit it.

- gentoo upstream bug 297933; filter BASHOPTS to keep bash 4.1 happy.

- correct an encoding issue in making binpkgs when an ebuild is utf8

- fix a traceback in pmerge -fK when trying to fetch required files for
  binpkgs.


--------------------------
pkgcore 0.5.6 (2009-12-13)
--------------------------

- tweak pkgcore configuration subsystem to tell you the parameter involved
  when it's passed an incorrectly typed object.

- fix an encoding issue w/ utf8 ebuilds on merging.


--------------------------
pkgcore 0.5.5 (2009-11-26)
--------------------------

- portage changed their flat_hash support a while back, specifically
  how mtime was stored.  We match that now (although it's daft to do so)
  for compatibility sake- primarily affected CVS users.

- removed a potential in the merge engine where triggers that didn't
  do an abspath on items they added could incorrectly be moved.
  Specifically affected FEATURES=debugedit for /usr/lib -> lib64 pathways.

- boolean restrictions now default to being finalized.

- pkgcore.fs.ops.offset_rewriter -> pkgcore.fs.contents.offset_rewriter

- various code cleanups, quite a few conversions to snakeoil.klass
  decorators/property tricks to simplify the code.

- experimental python3.1 support.  Bugs welcome, although till stated
  otherwise, it's considered unsupported.

- pkgcore.restrictions.values.ComparisonMatch has been removed.

- for overlayed repositories that have invalid atom stacking in their
  package.mask, give an appropriate error message indicating the file.

- gentoo bug 196561, PMS doesn't match portage behaviour for '~' atom
  operator.  Being that the pms definition has never been accurate, and
  portage hasn't handled '~' w/ a revision in any sane form, and finally
  do to portage adding a repoman check for this (bug 227225) pkgcore is
  now strict about disallowing revisions with '~'.  Scream at PMS to
  fix their doc if it's problematic.

- certain ebuilds (ssmtp for example) expect D to have a trailing '/'.
  Force this (outside pms compliance, so we match portage behaviour).


--------------------------
pkgcore 0.5.4 (2009-10-30)
--------------------------

- minor bug fix release fixing filter-env invocation (wasn't covered
  by tests)


--------------------------
pkgcore 0.5.3 (2009-10-30)
--------------------------

- filter-env grew a --print-vars option.  If you've been seeing
  "declare: write error: Broken pipe" from build operations, this should
  now be fixed via using this new option.

- the resolver wasn't properly accounting for planned modifications to
  the installed pkgs database.  If you've had upgrade issues from
  blockers, this is the root cause (pam/pambase in particular).

- eclass scanning is now JIT'd, and the resultant eclass dictionary
  is now marked immutable for safety reasons.

- for portage configuration when PORTDIR_OVERLAY is in use and portdir
  has a pregenerated cache, check the pregenerated cache first when
  looking for metadata.  This degrades the usage case where overlays
  override quite a few core eclasses in favor of the more common case
  where the pregenerated cache is the majority of the time, accurate.
  End result is upwards of a 2x reduction in open invocations.


--------------------------
pkgcore 0.5.2 (2009-10-28)
--------------------------

- touch vdb root on vdb modification as a way to notify alternative PMs
  that their cache needs updating.  Gentoo bug #290428.  Just leaves paludis
  to join in on the fun...

- portage 2.2 modified make.globals to add a default, non glep23 compliant
  ACCEPT_LICENSE.  pkgcore's implementation has been modified to be non
  compliant to glep23, matching portage semantics.

  If pquery <atom> has suddenly started returning nothing, this was the cause.

- fix a traceback that could occur when doing pmerge -pv for when binpkg
  repos were involved.


--------------------------
pkgcore 0.5.1 (2009-10-22)
--------------------------

- correct a python-2.6 incompatibility that rears its head when doing
  repository operations (installing, uninstalling, etc).


------------------------
pkgcore 0.5 (2009-10-22)
------------------------

- add protection against multiple python versions, w/ the default python
  invocation being a different major version from what pkgcore was installed
  under.  Primarily a fix to dohtml.

- ticket 230; tweaks for better >=python2.5 compatibility.

- pkgcore will now try to sync overlays if the overlay is a vcs.  This can
  be disabled by adding FEATURES="-autodetect-sync" to your make.conf

- pkgcore.sync.base.AutodetectSyncer was added as a way to pull configuration
  from existing on disk vcs repos, and generate a syncer from them.

- handle cache corruption a bit better- namely, log the warning, and keep
  going.  Degradation of performance can result, but it's preferable to just
  bailing.

- gentoo bug 280766; basically some ebuilds are sensitive to a trailing '/'
  on WORKDIR (portage strips it) leading to failures in path sedding.

- comply with PMS corner cases for package names; gentoo bug 263787

- serialization support for cpv derivatives.  Not great, but packages.g.o
  relies on it, thus its inclusion.

- not surprising on the timing (or spotting it via ciaran spreading it
  via blog comments), gentoo bug 226505 revisited- change in phase ordering
  afflicting all eapis.  pkgcore had it right the first time, inverted the
  ordering in 0.4.7.9.


-----------------------------
pkgcore 0.4.7.16 (2009-03-24)
-----------------------------

- pmerge is a bit more informative when there is nothing to merge,
  and doesn't ask if in --ask if the users wishes to proceed.
  Thanks to DJ Anderson for pointing out this oversight.

- ensure unicode for pquery --attr longdescription w/in pquery; via this
  it leaves the unicode question to the formatter, instead of down converting
  earlier.

- fix a mismatch between src ebuilds and binpkgs for _eclasses_ when
  doing pquery --attr inherited.  Bit of a hack, but it'll suffice.

- pquery --attr all and --attr allmetadata was added.  'all' gets you
  all known attrs (environment, contents, etc); bit heavy but useful if
  you need to see it all.  'allmetadata' gets you the key/val pairs for
  this host- fetchables, depends, slotting, eapi, repo, cbuild/chost, etc,
  but no environment/contents.

- fix cycle detection for dev-util/git; specifically there is a cycle on
  virtual/perl-Module-Built which can be ignored since that chain of deps
  are pulled in via post_rdepends.

- make gid/mode configurable for filelist pkgsets; this fixes 4 failures
  for when the tests are ran and the user isn't a member of portage.

- fix a cornercase in fs.livefs.intersect where intersecting a file/dir
  would trigger a traceback.

- fix a corner case where the world file isn't updated if the world file
  is empty.

- fix a deprecation warning under 2.6 caused by an impedence between
  native_PackageRestriction and the cpy version for __init__ invocation.

- fix gentoo bug 216492, a change in libsandbox behaviour- specifically
  libsandbox for >=1.3 is now appending libsandbox.so while failing to
  spot it already existing in LD_PRELOAD; pkgcore tests were written a bit
  strict thus were spotting this.  Loosen the test, and fix the case where
  a different preload is used in conjunction w/ sandbox.


-----------------------------
pkgcore 0.4.7.15 (2009-01-28)
-----------------------------

- fix docutils-0.5 incompatibility in build_api_docs.py

- python issue 4230 makes __getattr__ support descriptor protocol.
  This unfortunately causes part of config handling to go boom- fixed.

  Unfortunately this also means that we need to support both descriptor
  and *non* descriptor interpretters at *runtime*- if python is upgraded
  underfoot, things get unhappy to keep atom.__getattr__ from blowing up.
  Fixed either way.

- copy HOMEPAGE into vdb/binpkg by default.


-----------------------------
pkgcore 0.4.7.14 (2008-12-18)
-----------------------------

- profile awareness of eapi files, *including* strict validation.

- tighter use dep and atom support in pkgcore for specified eapis.

- ticket 187; fix a traceback when a specific subset of cycles are
  encountered.

- correct a python 2.6 incompatibility; object.__init__() is now strict
  about taking no keywords.


-----------------------------
pkgcore 0.4.7.13 (2008-10-29)
-----------------------------

- bug fix for transitive use atoms; if || ( a/b[x?] ), DepSet wasn't detecting
  that there were conditionals w/in it, as such wasn't doing evaluation.


--------------------------------------------------------
pkgcore 0.4.7.12 (2008-10-10) (2 hours after 0.4.7.11 ;)
--------------------------------------------------------

- security fix; force cwd to something controlled for ebuild env.  This
  blocks an attack detailed in glsa 200810-02; namely that an ebuild invoking
  python -c (which looks in cwd for modules to load) allows for an attacker
  to slip something in.


-----------------------------
pkgcore 0.4.7.11 (2008-10-10)
-----------------------------

- fix EAPI2 issues: default related primarily, invoke src_prepare for
  >=EAPI2 instead of >EAPI2.


-----------------------------
pkgcore 0.4.7.10 (2008-10-07)
-----------------------------

- fix in setup.py to install eapi/* files.
  die distutils, die.

- api for depset inspection for tristate (pcheck visibility mode) is fixed
  to not tell the consumer to lovingly 'die in a fire'.

- correct a failure in EAPI=2 src_uri parsing complaining about
  missing checksums for nonexistent files


----------------------------
pkgcore 0.4.7.9 (2008-10-06)
----------------------------

- eapi2 is now supported.

- DepSet has grown a temp option named allow_src_uri_file_names; this
  is to support eapi 2's -> SRC_URI extension.  This functionality
  will under go refactoring in the coming days- as such the api addition
  isn't considered stable.

- we now match the forced phase ordering portage induced via breaking
  eapi compatibilty for eapi0/1.

- tightened up allowed atom syntax; repository dep is available only when
  eapi is unspecified (no longer available in eapi2 in other words).
  atom USE dep parsing now requires it to follow slotting- this is done to
  match the other EAPI2 standard.

  Beyond that, better error msgs and tighter validation.


----------------------------
pkgcore 0.4.7.8 (2008-08-28)
----------------------------

- pkgcore now properly preserves ownership of symlinks on merging.
  ensure_perms plugins now need to handle symlinks (lchown at the least).

- free resolver caches after resolution is finished; lower the memory
  baseline for pmerge.

- fix up interface definitions for >snakeoil-0.2 dependant_methods changes.
  Via these cleanups and >snakeoil-0.2, memory usage is massively decreased
  for pmerge invocations.

- swallow EPIPE in pquery when stdout is closed early.


----------------------------
pkgcore 0.4.7.7 (2008-08-11)
----------------------------

- Disable fakeroot tests due to odd behaviour, and the fact it's currently
  unused.

- Fix installation issue for manpages for python2.4; os.path.join behaviour
  differs between 2.4 and 2.5.

- Kill off large memory leak that reared its head per pkg merge; still is
  a bit of a leak remaining, but nothing near as bad as before.


----------------------------
pkgcore 0.4.7.6 (2008-08-10)
----------------------------

- fix sandbox complaint when PORT_LOGDIR is enabled- sandbox requires abspath
  for any SANDBOX_WRITE exemptions, if PORT_LOGDIR path includes symlinks,
  force a `readlink -f` of the sandbox exemption.
  http://forums.gentoo.org/viewtopic-p-5176414.html

- ticket 213; if stricter is in FEATURES, fail out if insecure rpath is
  detected- otherwise, correct the entries.

- ticket 207; drop the attempted known_keys/cache optimizations, instead
  defer to parent's iterkeys always.  This eliminates the concurrency issue,
  and simplifies staleness detection.  Also kills off a tb for --newuse .

- ticket 201; pquery --restrict-revdep-pkgs wasn't behaving properly for
  slot/repository/user atoms, now does.

- Correct potential segfaults in cpython version of PackageRestriction and
  StrExactMatch's __(eq|ne)__ implementations.


----------------------------
pkgcore 0.4.7.5 (2008-07-06)
----------------------------

- incremental_expansion and friends have grown a cpython implementation-
  this speedup will show up if you are doing lots of profile work (pcheck
  for example, which has to read effectively all profile).

- if the invoking user isn't part of the portage group, don't throw a
  traceback due to permission denied for virtuals cache.

- correct a false positive in pkgcore.test.util.test_commandline that occurs
  when snakeoil c extensions aren't enabled.

- ticket 193; follow symlinks in /etc/portage/\*/ directories.

- ticket 203; functionfoo() {:;} is not function 'foo', it's 'functionfoo'.
  Users shouldn't have seen this- thanks to ferdy for spotting it in an audit.

- add 'skip_if_source' option to misc. binpkg merging triggers- defaults to
  True, controls whether or not if a pkg from the target_repo should be
  reinstalled to the repo.

- make contentsSet.map_directory_structure go recursive-
  this fixes ticket #204, invalid removal of files previously just merged.

- make --newuse work with atoms/sets

- add a cpy version of incremental_expansion

- fix longstanding bug - finalize settings from make.conf, stopping negations
  from being parsed twice. Without this fix, -* in a setting will negate
  random flags set after it.

- allow / in repo ids

- don't show flags from previous versions of packages in --pretend output -
  it's confusing and doesn't match portage behaviour.

- fix ticket 192: ignore nonexistent files in config protect checking


----------------------------
pkgcore 0.4.7.4 (2008-06-11)
----------------------------

- eapi1 bug fix; check for, and execute if found, ./configure if ECONF_SOURCE
  is unset.


----------------------------
pkgcore 0.4.7.3 (2008-05-16)
----------------------------

- ticket #185; tweak the test to give better debug info.

- add proper handling of very, very large revision ints (up to 64 bits).

- fakeroot tests are enabled again.

- misc bug fixes; pquery --revdep traceback, vecho complaints from do*
  scripts.

- explicit notice that Jason Stubbs, Brian Harring, Andrew Gaffney, and
  Charlie Shepherd, Zac Medico contributions are available under either
  GPL2 (v2 only) or 3 clause BSD.
  Terms are in root directory under files names BSD, and GPL2.
  Aside from the bash bits Harring implemented during the EBD days, the
  remaining ebuild bash bits are Gentoo Foundation copyright (GPL2), and
  the contributions from Marien Zwart are currently GPL2 (config bits, still
  need explicit confirmation).

  What that effectively means is that pkgcore as a whole currently is GPL2-
  sometime in the near future, the core of pkgcore (non-ebuild bits) will be
  BSD/GPL2, and then down the line the bash bits will be rewritten to be
  BSD/GPL2 (likely dropping the functionality it uses down to something bash/
  BSD shell compatible).

- expansion of -try/-scm awareness to installed pkgs database.  Binpkg
  repositories now abid by ignore_paludis_versioning also.

- ticket #184; silence disable debug-print in non build/install phases.

- handle malformed rsync timestamps more cleanly.


----------------------------
pkgcore 0.4.7.2 (2008-05-07)
----------------------------

- new portage configuration feature- 'ignore-paludis-versioning'.  This
  directs pkgcore to ignore nonstandard -scm ebuilds instead of complaining
  about them.
  Note this does *not* affect the installed pkgs database- if there is a
  -scm ebuild in the vdb, pkgcore *must* deal with that ebuild, else if it
  silently ignores vdb -scm pkgs it can result in overwriting parts of the
  -scm pkg, and other weirdness.  If you've got a -scm version pkg installed,
  it's strongly suggested you uninstall it unless you wish to be bound to that
  nonstandard behaviour of paludis.

  Finally, it's not yet covering *all* paludis version extensions- that will
  be expanded in coming versions.

- pkgcore is now aware of installed -scm pkgs, and gives a cleaner error
  message.

- a few versions of portage-2.2 automatically added @PKGSET items to the
  world file; due to how portage has implemented their sets, this would
  effectively convert the data to portage only.  As such, that feature was
  reversed (thank you genone); that said, a few world files have @pkgset
  entries from these versions.  Pkgcore now ignores it for worldfiles, and
  levels a warning that it will clear the @pkgset entry.

- ticket #174; ignore bash style comments (leading #) in pkgsets, although
  they're wiped on update.  If folks want them preserved, come up with a way
  that preserves the location in relation to what the comment is about- else
  wiping seems the best approach.

- ticket #14; tweak PORT_LOGDIR support a bit, so that build, install,
  and uninstall are seperated into different logs.

- added '@' operator to pmerge as an alias for --set; for example,
  'pmerge @system' is the same as 'pmerge --set system'.

- fallback method of using the file binary instead of libmagic module is
  fixed; ticket #183.


----------------------------
pkgcore 0.4.7.1 (2008-05-04)
----------------------------

- correct a flaw in repository searching that slipped past the test harness.
  effectively breaks via inverting the negate logic for any complex search.


--------------------------
pkgcore 0.4.7 (2008-05-03)
--------------------------

- prepstrip was updated to match current portage semantics, minus stripping
  and splitdebug functionality (we handle that via a trigger).  Via this,
  FEATURES=installsources and basic bincheck (pre-stripped binaries) is now
  supported.

- FEATURES='strip nostrip splitdebug' are now supported in portage
  configuration (trigger is pkgcore.merge.triggers.BinaryDebug).

- added cygwin ostype target for development purposes.  In no shape or form
  is this currently considered supported, although anyone interested in
  developing support for that platform, feel free to contact us.

- in candidate identification in repository restriction matching, it was
  possible for a PackageRestriction that was negated to be ignored, thus
  resulting in no matches.  This has been corrected, although due to
  collect_package_restrictions, it's possible to lose the negation state
  leading to a similar scenario (no known cases of it currently).  This
  codepath will need reworking to eliminate these scenarios.

- mercurial+ sync prefix is now supported for hg.

- triggers _priority class var is now priority; overload with a property if
  custom functionality is needed.


--------------------------
pkgcore 0.4.6 (2008-04-29)
--------------------------

- filelist sets (world file for example) are now sorted by atom comparison
  rules.  ticket #178.

- pquery --restrict-revdep-pkgs and --revdep-pkgs were added: they're
  used to first match against possible pkgs, then do the revdep looking for
  pkgs that revdep upon those specific versions.  Functionality may change,
  as may the outputting of it.  ticket #179.

- pebuild breakage introduced in 11/07 is corrected; back to working.

- 'info' messages during merging are now displayed by default- new debug
  message type was added that isn't displayed by default.

- ebuild domain now accepts triggers configuration directive.

- FEATURES=unmerge-buildpkg was added; this effectively quickpkgs a pkg
  before it's unmerged so you have a snapshot of its last state before
  it is replaced.

- FEATURES=pristine-buildpkg was added; this is like FEATURES=buildpkg,
  but tbzs the pkg prior to any modification by triggers.  Upshot of this,
  you basically have an unmodified binpkg that can be localized to the merging
  host rather then to the builder.  Simple example, with this if your main
  system is FEATURES=strip, it tucks away a nonstripped binpkg- so that
  consumers of the binary repo are able to have debug symbols if they want
  them.

- FEATURES=buildsyspkg is now supported.

- FEATURES=buildpkg is now supported.

- the engine used for install/uninstall/replace is now configurable via
  engine_kls attribute on the op class.

- dropped exporting of USER='portage' if id is portage.  Ancient var setting,
  can't find anything reliant on it thus punting it.

- add SunOS to known OS's since its lchown suffices for our needs.

- added eapi awareness to atoms, so that an eapi1 atom only allows the
  slot extension for example.

- remove a stray printf from cpy atom; visible only when repository atoms
  are in use.


--------------------------
pkgcore 0.4.5 (2008-04-09)
--------------------------

- fix collision unprotect trigger exceptions (typically KeyError).
  ticket #165

- correct invalid passing of force keyword down when the repository isn't
  frozen.  Occasionally triggered user visible tracebacks in pmaint copy.

- portage broke compatibility with pkgcore a while back for our binpkgs-
  for some inane reason, portage requires CATEGORY and PF in the xpak
  segment.  This is being removed from portage in 2.2, but in the interim
  pkgcore now forces those keys into the binpkgs xpak for compatibility
  with portage.

  Shorter version: pmaint copy generated binpkgs work with portage again.

- cbuild/chost/ctarget are available via pquery --attr, and are written to
  binpkg/vdb now.

- stat removal work: FEATURES=-metadata-cache reuses existing eclass cache
  object, thus one (and only one) scan of ${PORTDIR}/eclass

- metadata, flat_hash, and paludis_flat_list cache formats configuration
  arg 'label' is no longer required, and will be removed in 0.5.  If they're
  unspecified, pkgcore will use location as the place to write the cache at,
  else it'll combine location and label.

- cdb, anydbm, sqlite, and sql_template cache backends have been removed
  pending updating the code for cache backend cleanups.  If interested in
  these backends, contact ferringb at irc://freenode.net/#pkgcore .


--------------------------
pkgcore 0.4.4 (2008-04-06)
--------------------------

- merging/replacing performance may be a bit slower in this release- the level
  of stats calls went up in comparison to previous releases, with several
  duplicates.  This will be corrected in the next release- releasing in the
  interim for bugfixes this version contains.

- add CBUILD=${CBUILD:-${CHOST}}; couple of odd ebuilds rely on it despite
  being outside of PMS.

- protective trigger was added blocking unmerging of a basic set of
  directories/syms; mainly /*, and /usr/*.

- when a merge passes through a symlink for path resolution, that sym is
  no longer pulled in as an entry of that pkg.  Originally this was done for
  protective reasons, but it serves long term as a way to inadvertantly hold
  onto undesired junk from the users fs, and opens the potential to unmerge
  system/global symlinks when that pkg/slot's refcount hits zero.

- detection, and predicting merge locations for syms was doing an unecessary
  level of stat calls; this has been reduced to bare minimum.

- ticket 159; force an realpath of CONTENTS coming from the vdb due to other
  managers not always writing realpath'd entries, thus resulting in occasional
  misidentification of what to remove.

- pkgcore.util.parserestrict no longer throws MalformedAtom, always
  ParseError.  Removes ugly commandline tracebacks for bad atoms supplied
  to pmerge.

- ticket 158; honor RSYNC_PROXY for rsync syncer.
  Thanks to user Ford_Prefect.

- pmerge -N now implies --oneshot.

- correct a flaw in tbz2 merging where it repeatedly try to seek in the bz2
  stream to generate chksums, instead of using the on disk files for
  chksumming.

- pmaint regen w/ > 1 thread no longer throws an ugly set of tracebacks upon
  completion.

- binpkg repositories now tell you the offending mode, and what is needed
  to correct it.  No longer cares if the specified binpkg base location is
  a symlink also.

- pmaint --help usage descriptions are far more useful now.


--------------------------
pkgcore 0.4.3 (2008-03-31)
--------------------------

- correct a corner case where a users bash_profile is noisy, specifically
  disable using $HOME/.bashrc from all spawn_bash calls.

- USE=-* in make.conf support is restored.  ticket 155.

- minor tweak to package.keywords, package.use, and package.license support-
  -* is properly supported now.  Following portage, if you're trying to
  match keywords for a pkg that are '-* x86', you must match on x86.

- pquery --attr use output for EAPI=1 default IUSE is significantly less
  ugly.

- ticket #150. EAPI1 IUSE defaults fixups.  stacking order is that default
  IUSE is basically first in the chain, so any configuration (global, per
  pkg, etc), will override if possible.  Effectively, this means a default
  IUSE of "-foon" is pointless, since there is no earlier USE stack to
  override.

- pkgcore.ebuild.collapsed_restrict_to_data api was broken outside of a
  major version bump- specifically pull_cp_data method was removed since
  the lone consumer (pkgcore internals) doesn't need it, and the method
  is semi dangerous to use since it only examines atoms.


--------------------------
pkgcore 0.4.2 (2008-03-30)
--------------------------

- correct handling of ebuilds with explicit -r0 in filename, despite it being
  implicit.  Thanks to rbrown for violating gentoo-x86 policy out of the blue
  w/ an ebuild that has -r0 explicit in the filename for smoking out a bug
  in pkgcore handling of it.  Ebuild since removed, but the KeyError issue
  is corrected.  (keep the bugs coming)

- minor performance optimization to binpkg merging when there is a large #
  of symlink rewrites required.

- ticket #153; restore <0.4 behaviour for temporal blocker validation, rather
  then invalidly relying on the initial vdb state for blocker checks.  Fixes
  resolution/merging of sys-libs/pam-0.99.10.0


--------------------------
pkgcore 0.4.1 (2008-03-20)
--------------------------

- add tar contentsSet rewriting; tarballs sometimes leave out directories,
  and don't always have the fully resolved path- /usr/lib/blah, when
  /usr/lib -> /usr/lib64 *should* be /usr/lib64/blah, but tar doesn't force
  this.  Due to that, can lead to explosions in unpacking- this is now fixed.

- pquery --attr inherited was added; this feature may disappear down the
  line, adding it meanwhile since it's useful for ebuild devs.

- adjust setup.py so that man page installation properly respects --root

- correct a corner case where a package name of 'dev-3D' was flagged as
  invalid.


------------------------
pkgcore 0.4 (2008-03-18)
------------------------

- resolver fixes: vdb loadup wasn't occuring for old style virtuals for
  rdepend blockers, now forces it.  It was possible for a node to be
  considered usable before its rdepends blockers were leveled- now those
  must be satisfied before being able to dep on the node.

- resolver events cleanup; pmerge now gives far better info as to why a
  choice failed, what it attempted to get around it, etc.

- multiplex trees now discern their frozen state from their subtrees,
  and will execute the repo_op for the leftmost subtree if unfrozen.

- pquery --attr eapi was added.

- ticket 94; package.provided is now supported fully both in profiles,
  and in user profile (/etc/portage/profile).

- ticket 116; ignore empty tarfile exception if the exception explicitly
  states empty header.

- utter corner case compatibility- =dev-util/diffball-1.0-r0 is now the
  same as =dev-util/diffball-1.0 .

- convert FETCHCOMMAND/RESUMECOMMAND support to execute spawn_bash by
  default instead of trying to cut out shell; this kills off the occasional
  incompatibility introduced via portage supplying make.globals.

- FEATURES=sfperms is now a trigger instead of a dyn_preinst hook.
  Faster, cleaner, etc.

- delayed unpacking of binpkgs has been disabled; occasionally can lead to
  quadratic behaviour in contents accessing, and extreme corner case trigger
  breakages.  Will be re-enabled once API has been refactored to remove
  these issues.

- FEATURES=multilib-strict was converted into a trigger.  Tries to
  use the python bindings for file first (merge file[python]), falling
  back to invoking file.  Strongly suggested you have the bindings- fair bit
  faster.  Finally, verification now runs for binpkgs also.

- bug 137; symlink on directory merging failures where pkgcore would wipe
  files it had just installed invalidly.

- correct issue in offset rewriting (was resetting new_offset to '/')-
  should only be api visible, no existing consumers known.

- ebuild env lzma unpack support was broken; fixed (ticket 140).

- Additional debug output for pmerge.

- Further extending PortageFormatter to sanely handle worldfile highlights
  and show repos with both id and location

- Ticket 132: Portage Formatter supports real portage colors now,
  thanks to agaffney for getting the ball rolling

- Masked IUSEs were not treated right in all cases, thanks to agaffney
  for report and help testing

- diefunc tracebacks beautified


--------------------------
pkgcore 0.3.4 (2007-12-26)
--------------------------

- IUSEs were filtered, unstated were not respected though breaks with
  current portage tree, so re-enabling.
  Also sanely handle -flag enforcing now and kill hackish code for it.


--------------------------
pkgcore 0.3.3 (2007-12-14)
--------------------------

- IUSE defaults are respected now, so EAPI=1 implemented

- Write slotted atoms to worldfile as portage supports this now

- Sync up with portage; add support for lzma to unpack- mirror r7991 from
  portage.


--------------------------
pkgcore 0.3.2 (2007-11-03)
--------------------------

- ticket 190746 from gentoo; basically need to force the perms of first level
  directory of an unpacked $DISTDIR to ensure it's at least readable/writable.
  fixes unpacking of app-misc/screen-4.0.3_p20070403::gentoo-x86 .

- ticket 118; if -u, don't add the node to world set.

- correct a corner case in python implementation of cpv comparison (just
  python, cpy extension handles it correctly); bug 188449 in gentoo, basically
  floats have a limited precision, thus it was possible to get truncation in
  comparison with specially crafted versions.

- handle EOF/IOError on raw_input (for --ask) a bit more gracefully, ticket
  108.

- cd to ${WORKDIR} if ${S} doesn't exist for test/install phases; matches
  change in portage behaviour.

- Now require snakeoil version 0.2 and up- require new capability of
  AtomicWriteFile, ability to specify uid/gid/perms.  Via that, fixes ticket
  109 (umask leaking through to profile.env).

- the 'glsa' pkgset is now deprecated in favor of 'vuln'; will remain
  through till 0.4 (ticket #106).

- ticket 105/96; fix via andkit, basically a bug in einstall lead to
  extra einstall opts getting dropped instead of passed through.

- compatibility fix for lha unpacking for nwere versions of lha.

- emake now invokes ${MAKE:-make}, instead of make- undocumented ebuild
  req, see bug 186598 at bugs.gentoo.org.

- pmerge --verbose is now pmerge -F portage-verbose-formatter

- Stop installing pregen symlink; functionality moved to pmaint regen.

- 'pmerge --domain' was added; basically is a way to specify the domain to
  use, else usees the configuration defined default domain.

- new ebuild trigger to avoid installing files into symlinked dir (get_libdir
  is the friend to fix a common /usr/lib -> /usr/lib64 bug), ticket 119


--------------------------
pkgcore 0.3.1 (2007-06-27)
--------------------------

- ticket 86; export FILE for portage_conf FETCHCOMMAND/RESUMECOMMAND support,
  convert from spawn_bash to spawn, add some extra error detection

- Correct cleanup of unknown state ebp processors; basically discard them if
  they fail in any way.  Cleanup inherit error msg when under ebd.

- Correct permission issue for vdb virtuals cache.

- ticket 84; rework overlay internals so that sorting order can't accidentally
  expose a version masked by a higher priority repository in an overlay stack.


------------------------
pkgcore 0.3 (2007-06-06)
------------------------

- pregen has moved into pmaint regen.

- Several example scripts that show how to use the pkgcore api have been
  added, among others:
  - repo_list (lists repos and some of their attributes)
  - changed_use (a poor man's --newuse)
  - pkg_info (show maintainers and herds of a package)
  - pclean (finds unused distfiles)

- Pkgcore now supports several different output formats for the buildplan.
  Portage and Paludis emulation are the notable formats, though plan
  category/package and the original output are also available as options.

- Portage formatter is now the default.

- Pkgcore formatter (no longer default) output was simplified to be less
  noisy.

- Large grammar fixes for documentation.

- Miscellaneous pylint cleanups, including whitespace fixes.

- Most of pkgcore.util.* (mainly the non pkgcore-specific bits) have been
  split out into a separate package, snakeoil. This includes the relevant cpy
  extensions.

- Triggers are quieter about what they're doing by default.

- /etc/portage/package.* can now contain unlimited subdirectories and
  files (ticket 71).

- livefs functionality is no longer accessible in pkgcore.fs.*; have to access
  pkgcore.fs.livefs.*

- old style virtual providers from the vdb are now preferred for newer versions
  over profile defined defaults.

- added profile package.use support.

- ticket 80; $REPO_LOC/profiles/categories awareness; if the file exists, the
  repo uses it by default.

- resolver refactoring; report any regressions to ferringb.  Integrated in
  events tracking, so that the choices/events explaining the path the resolver
  took are recorded- via this, we actually have sane "resolution failed due to"
  messages, adding emerge -pt/paludis --show-reasons is doable without hacking
  the resolver directly, spotting which pkgs need to be unmasked/keyworded for
  a specific request to be satisfied, etc, all of it is doable without having
  to insert code directly into the resolver.  Anyone interested in adding these
  featues, please talk to harring.
  Worth noting, the events api and data structs for the resolver are still a
  work in process- meaning the api is not guaranteed to stay stable at least
  till the next minor release.

- old style virtual pkgs are no longer combined into one with multiple
  providers; aside from simplifying things, this fixes a few annoying resolution
  failures involving virtual/modutils.


---------------------------
pkgcore 0.2.14 (2007-04-08)
---------------------------

- correct potential for profile path calculation screwup.

- refactor isolated-functions.sh so all internal vars are prefixed with
  PKGCORE_RC\_; shift vars filter to PKGCORE_RC\_.* instead of RC\_.* .
  If you were having problems building courier-imap (RC_VER variable),
  this fixes it.

- better interop with paludis VDB environment dumps.

- treat RESTRICT as a straight depset for UI purposes (minor, but looks
  better this way).


---------------------------
pkgcore 0.2.13 (2007-03-30)
---------------------------

- Added '~' to allowed shlex word chars.

- Due to amd64 /lib -> /lib64, change the default policy for sym over
  directory merging to allow it if the target was a directory.


---------------------------
pkgcore 0.2.12 (2007-03-29)
---------------------------

- Ensure PackageRestriction._handle_exceptions filters the check down to
  just strings; if running pure python, this could trigger a traceback
  via the python native native_CPV.__cmp__.

- Tweak python native native_CPV.__cmp__ to not explode if given an instance
  that's not a CPV derivative.

- Reorder ||() to use anything matched via the current state graph, aside
  from normal reordering to prefer vdb.

- default mode for ensure_dirs is now 0755.

- Work around broken java-utils-2.eclass state handling in
  java-pkg_init_paths\_; tries to access DESTTREE in setup phase, which
  shouldn't be allowed- fix is temporarily shifting the DESTTREE definition
  to pre-ebuild sourcing so that it behaves.

  Will be removed as soon as the eclass behaves is fixed.


---------------------------
pkgcore 0.2.11 (2007-03-27)
---------------------------

- COLON_SEPARATED, not COLON_SEPERATED for env.d parsing.

- fix ticket #74; "x=y@a" should parse out as 'y@a', was terminating
  early.


---------------------------
pkgcore 0.2.10 (2007-03-27)
---------------------------

- FEATURES=ccache now corrects perms as needed for when userpriv toggles.

- shift PORTAGE_ACTUAL_DISTDIR and DISTDIR definition into the initial env,
  so that evil git/subversion/cvs class can get at it globally.

- pquery --attr repo now returns the repo_id if it can get it, instead of
  the str of the repo object.

- OR grouppings in PROVIDES was explicitly disabled; no ebuild uses it, nor
  should any.


--------------------------
pkgcore 0.2.9 (2007-03-19)
--------------------------

- convert use.mask/package.use.mask, use.force/package.use.force stacking
  to match portage behaviour- basically stack use.* and package.* per profile
  node rather then going incremental for use.*, then package.* .  If you were
  having issues with default-linux/amd64/2006.1 profile and sse/sse2 flags for
  mplayer, this ought to correct it.

- add USE conditional support to RESTRICT.

- fix noisy regression from 0.2.8 for temp declare overriding; if you saw lots
  of complaints on env restoration, corrects it.  Superficial bug, but rather
  noisy.

- Fix a bug for binpkg creation where PROVIDES gets duplicated.

- Bit more DepSet optimizations; specifically collapses AND restriction into
  the parent if it is also an AND restriction.

- make --no-auto work correctly for pebuild

- delay DISTDIR setup till unpack phase to prevent any invalid access; also
  takes care of a pebuild traceback.


--------------------------
pkgcore 0.2.8 (2007-03-17)
--------------------------

- fix bug so that 6_alpha == 6_alpha0 when native_CPV is in use; only possible
  way to have hit the bug is having all extensions disabled (CPY version gets it
  right).

- add a trigger to rewrite symlink targets if they point into ${D}

- info trigger now ignores any file starting with '.'; no more complaints about
  .keep in info dirs.

- if an ebuild has a non-default preinst and offset merging, a rescan of ${D}
  is required- offset wasn't being injected, fixed.

- if offset merging for a binpkg, reuse the original contentsSet class-
  this prevents quadratic (worst case) seeking of the tarball via preserving
  the ordering.

- if merging a binpkg and a forced decompression is needed, update the
  cset in memory instead of forcing a scan of ${D}.

- misc filter-env fixes, cleanup, and tests.

- change var attr (exported/readonly) env storage to better interop with
  the others; internally, we still delay the var attr/shopt resetting till
  execution.

- misc initialization fixes to syncers for when invoked via GenericSyncer.
  If previously layman integration wasn't working for you, should now.

- shift the misc fs property triggers to pre_merge, rather then sanity_check;
  sanity_check should be only for "do I have what I need to even do the merge?"
  and minimal setup for the op (for example, transfering files into workdir).
  Running preinst was occasionally wiping the changes the triggers made, thus
  allowing screwed up ebuilds with custom preinst's to slip in a portage gid
  for merge.

- fix a corner case for cpy join spotted by TFKyle where length calculation
  was incorrect, leading to a trailing null slipping into the calculated
  path.

- fix bash parsing for a corner case for empty assigns; literally,
  x=
  foo='dar'
  would incorrectly interpret x=foo, instead of x=''.


--------------------------
pkgcore 0.2.7 (2007-03-04)
--------------------------

- layman configuration (if available) is now read for portage configuration
  for sync URI for overlays.  tar syncer is currently unsupported; others may
  be buggy.  Feed back desired (author doesn't use layman).  Ticket #11.  If
  you want it disabled, add FEATURES=-layman-sync .

- another fix for daft tarballs that try to touch cwd.


--------------------------
pkgcore 0.2.6 (2007-03-04)
--------------------------

- make intersecting ~ and =* atoms work again (used by pquery --revdep)

- catch a corner case py2.5 bug where AttributeError bleeds through from
  generic_equality.

- Via solars prodding, finished up the remaining bits for ROOT support.

- resolver traceback for if a requested atom is already known as insoluable.
  Thanks to kojiro for spotting it.

- misc bash code cleanup.

- PATH protection has been loosened slightly to enable 'weird' eclasses that
  are doing global PATH mangling.

- $HOME location for building was shifted into the targeted packages
  directory, rather then a shared within $PORTAGE_TMPDIR.

- setgid/setuid triggers now match portage behaviour; -s,o-w mode change.

- trigger warnings are now enabled.

- New default trigger added; CommonDirectoryModes, checks for common
  directories (/usr, /etc, /usr/bin, /usr/lib for example) in the merge set,
  checking the packages specified modes for them.  If not 0755, throws a
  warning.

- For directory on directory merging, ensure_perms (default op) was changed
  to preserve the existing directories permissions.  Generally speaking, this
  means that later versions of an ebuild have to use post_inst to correct the
  perms if they're incorrect- previously, the new perms/mode were forced on
  the existing.  Several common ebuilds (openssl for example) will generate
  weird modes on common directories however (heavily restricted perms), which
  can break things.  For the time being, the default is scaled down to the
  looser form portage does.

- added man page generation: pquery, pmerge

- pconfig now has a "dump-uncollapsed" command to dump the "raw" config.

- pebuild now supports --no-auto to run just the targeted phase.

- mass expansion of test coverage: pkgcore.restrictions.*,
  pkgcore.util.*, pkgcore.ebuild.*

- minor cleanup of pkgcore.test.ebuild.test_cpv to reduce redundant data sets;
  total testcase runtime reduction by about a third.

- diverge from unittest.TestCase to provide extra checks for normal asserts-
  assertNotEqual for example, checks both __eq__ and __ne__ now to smoke out
  any potential oversights in object equality implementation.

- use nsec mtime resolution if available to match python stdlib.

- env var PORTAGE_DEBUG for controlling how much debug info the ebuild env
  generates is now PKGCORE_DEBUG; range is the same, 0 (none), 1 (just the
  ebuild/eclass), 2 (1 + relevant setup code), 3 (2 + filter-env data),
  4 (everything).


--------------------------
pkgcore 0.2.5 (2007-02-19)
--------------------------

- handle corner case in depend cycle processing where a package directly
  depends upon itself; fixes processing of sys-devel/libtool specifically.

- for pquery --attr keywords, sort by arch, not by stable/unstable.

- correct misc corner case atom bugs; an intersection bug, miss on an invalid
  use dep atom lacking a closure in cpy atom, verification of use chars in
  native atom,

- osutils extensions tests, correcting a few cpy differences in behaviour from
  native.

- For unpacking a tarball that doesn't have its files in a subdir, tar will
  occasionally try to utime the cwd resulting in a failure- uid owner for
  WORKDIR was changed to allow tar to do the utime, thus succeed in unpacking.
  Only visible for userpriv and with oddball packages, gnuconfig for example.

- Cleanup of a few slow test cases; running the test suite should now be around
  25%-33% faster.


--------------------------
pkgcore 0.2.4 (2007-02-16)
--------------------------

- refactoring of trigger implementations- cleanup and tests.  Additionally,
  eliminate a potential mtime based frace if the underlying fs (or python
  version) doesn't do subsecond resolution.

- force FEATURES into the exported ebuild env always.

- for pmerge -p $target, which prefers reuse normally, *still* prefer the
  highest versions, just examine vdb first, then nonvdb.

- minor optimization in readlines usage in the backend; kills off a duplicate
  stat call.

- if a stale cache entry is detected, and the backend is writable, wipe the
  cache entry.  Little bit slower when detected, but saves parsing the file
  next time around.


--------------------------
pkgcore 0.2.3 (2007-02-12)
--------------------------

- support for ** in package.keywords

- export preparsed SLOT to ebuild env; ebuilds shouldn't rely on this
  since it can lead to fun metadata issues, but certain eclasses do.

- fix exporting finalized form of RESTRICT to the build env; ticket 61.

- fix for RESTRICT=fetch to not treat the filename as a uri.

- expose the full make.conf environment to FETCHCOMMAND and RESUMECOMMAND-
  ticket 58

- added support for make.conf defined FETCH_ATTEMPTS; max # of unique uris to
  attempts per file before giving up, defaults to 10.

- added int_parser type for config instantiation definitions (ConfigHint),
  and usual introspection support.

- fix regression limiting satisifiers for depends to installed only in corner
  case installed bound cycles; automake/perl specifically trigger this, thus
  most folks should have seen it if using -B.

- Better handling of non-ascii characters in metadata.xml.


--------------------------
pkgcore 0.2.2 (2007-01-30)
--------------------------

- The terminfo db is now used for xterm title updates. If title updates
  worked in pkgcore 0.2 or 0.2.1 and no longer work in 0.2.2 file a bug and
  include the TERM environment variable setting.

- misc fixup for asserts in cpy code when debugging is enabled, and closing
  directory fds when corner case error paths are taken (out of memory for
  example).

- atoms are picklable now.

- add tests for pmaint copy (quickpkg equivalent), and add
  --ignore-existing option to copy just pkgs that don't exist in the
  target repo.

- fix pmerge handling of --clean -B for automake and a few other DEPEND level
  hard cycles.


--------------------------
pkgcore 0.2.1 (2007-01-24)
--------------------------

- fix corner case for portage configuration support; old system (<=2004)
  installations may have /etc/portage/sets/world, which confused pmerges
  world updating, leading to writing bad entries.  Ticket 54.

- fix issues with distcc/ccache (ticket 55) so that they actually work.

- fix pconfig dump traceback; ticket 56.


------------------------
pkgcore 0.2 (2007-01-22)
------------------------

- glsa pkgset will now include metadata/glsa from overlays.

- pmaint script; tool for --sync'ing, doing quickpkging, moving packages
  between repos for repository conversions. General repository maintenance.

- sync subsystem: supports bzr, cvs, darcs, git, mercurial (hg), rsync,
  and subversion.

- binpkg repositories now support modification; FEATURES=buildpkg basically

- binpkg contents handling is significantly faster.

- pmerge:

  - supports --ask (thanks to nesl247/alex heck)
  - pmerge --replace is default now; use --noreplace for original behaviour.
  - 'installed' set was added; is a pkgset comprised of all slotted atoms from
    the vdb; useful for pmerge -u to enable upgrades of *everything* installed.
  - versioned-installed set was added; useful for -e, this set is compromised
    of exact version of everything installed.
  - added --with-built-depends, -B; resolver defaults to ignoring 'built'
    ebuild depends (those from vdb, from binpkgs for example), this option
    tells it to update those depends.

- xterm titles

- massive resolver cleanup, and general fixes.

- rewritten plugins system, register_plugins is no longer used.

- paludis flat_list cache read/write support.

- portage flat_list cache write support (cache used for
  $PORTDIR/metadata/sync)

- pebuild/pregen/pclone_cache: heavy UI cleanup.

- pquery:

  - prettier printing of depends/rdepends/post_rdepends under -v
  - print revdep reasons
  - now requires an arg always; previously defaulted to '*', which is
    still supported but also accessible via --all .
  - added --maintainers-email and --maintainers-name; use case insensitive
    regex by default for --maintainer style options.

- added repo_id atom extension; see doc/extended-atom-syntax.rst for details.
  short version, sys-apps/portage::gentoo would match portage *only* from
  `gentoo` repository.

- overlays now combine mirror targets from their parent repository, and
  from their own repository data.

- configuration subsystem:

  - configuration: lazy section refs were added (lazy_ref), useful for when
    the object arguement needs to be instantiated rarely (syncers for
    repositories for example).

  - mke2fs (literal /etc/mke2fs.conf file) akin configuration format was
    added, pkgcore.config.mke2fsformat.config_from_file.

- expanded test coverage.

- merged standalone test runner into setup.py; prefered way of running it is
  `python setup.py test` now.

- ongoing portage configuration support additions-

  - FEATURES=collision-protect support
  - INSTALL_MASK support, FEATURES noinfo, nodoc, and noman support.
  - /etc/portage/package.* files can be directories holding seperate files
    to collapse

- gnu info regeneration trigger added.

- performance improvements:

  - cpython extensions of select os.path.* functionality; 20x boost for what
    was converted over (stdlib's posix module is a bit inefficient).

  - cpython extension for file io in pkgcore.util.osutils: 7x faster on ENOENT
    cases, 4x-5x on actual reading of small files (think cache files).  If
    iterating over lines of a file, use pkgcore.util.osutils.readlines- again,
    faster then standard file object's equivalent- 3x reduction (7.6ms to 2.5ms
    for full contents  reading).

  - partial cpython reimplementation of atom code; mainly parsing, and
    critical __getattr__ invocation (2+x faster parse).

  - partial cpython reimplementation of depset code; strictly just parsing.
    Faster (given), but mainly is able to do optimizations to the depset
    cheaply that python side is heavily slowed down by- ( x ( y ) ) becomes
    ( x y ) for example.

  - chunks of restriction objects were pushed to cpython for memory reasons,
    and bringing the instantiation cost down as low as possible (the common
    restrict objects now are around 1-3us for new instantation, .5 to 1us
    for getting a cached obj instead of instantiating).

  - bug corrected in base repo classes identify_candidates method; should now
    force a full walk of the repo only when absolutely required.

  - chksuming now does a single walk over a file for all checksummers,
    instead of one walk per checksummer- less disk thrashing, better
    performance.

  - vdb virtuals caching; massive performance boost via reduced IO.  Relies on
    mtime checks of vdb pkg directories for staleness detection,
    auto-regenerating itself as needed.

- heavy profile code cleanup; should only read each common profile node once
  now when loading up multiple profiles (pcheck).  Far easier code to read
  in addition.

- cache eclass staleness verification now relies on mtime comparison only-
  allows for eclasses to move between repos; matches portage behaviour.

- pkgcore.util.caching.*, via __force_caching__ class attr in consumers, can
  be used to force singleton instance creation/caching (error if unhashable).

- ebuild support:

  - PORTAGE_ACTUAL_DISTDIR was reenabled, thus cvs/svn equivalent ebuilds are
    usable once again.
  - fixed pkgcore's pkgcore emulation of has_version/best_version matching
    behaviour for old style virtuals to match portages (oddity, but ebuilds
    rely on the goofy behaviour).
  - various fixups to unpack function; should match portage behaviour as of
    01/07 now.
  - if FEATURES=test, set USE=test; if USE=test has been explicitly masked for
    a package, disable src_test run; matches portage 2.1.2 behaviour.
  - cleanup build directory, and unmerge directories upon finishing

- filter-env now is accessible directly via python; pkgcore.ebuild.filter_env.
  Needs further work prior to being usable for pcheck inspection of ebuilds,
  but it's a good start.


--------------------------
pkgcore 0.1.4 (2006-10-24)
--------------------------

- Compatibility with caches written by portage 2.1.2_pre3-r8.


--------------------------
pkgcore 0.1.3 (2006-10-24)
--------------------------

- Always process "|| ( a b )" in the right order.

- Fix disabling a flag in package.use.mask or package.use.force.


--------------------------
pkgcore 0.1.2 (2006-10-10)
--------------------------

- Make filter_env work on hppa (and possibly more architectures) where using
  python CFLAGS for this standalone binary does not work.

- Fall back to plain text output if the TERM variable is unsupported.

- Deal with dangling symlinks in binpkg repositories.

- Fix expanding of incrementals (like USE) in make.defaults.

- pquery: support --attr fetchables, handle extra commandline arguments as
  -m or --expr restrictions.

- USE deps once again allow setting a flag only if it is actually settable
  on the target package.


--------------------------
pkgcore 0.1.1 (2006-10-02)
--------------------------

- hang fix for test_filter_env

- package.keywords fixes: no longer incremental, supports '*' and '~*'
  properly

- FEATURES="userpriv" support works again.

- pmerge repository ordering now behaves properly; prefers src ebuilds, then
  built pkgs; -k inverts that (previously was semi-undefined)

- binpkg fixes: run setup phase

- replace op fixes: force seperate WORKDIR for unmerge to protect against
  env collisions

- loosened category rules: allow _. chars to support cross-dev hack.

- build fixes: make $A unique to avoid duplicate unpacks; force distdir
  creation regardless of whether or not the pkg has any stated SRC_URI
  (fixes cvs and subversion eclsas usage).  Fix sandbox execution to chdir
  to an existent directory (sandbox will fail if ran from a nonexistent dir).

- change DelayedInstantiation objects to track __class__ themselves; this
  fixes pquery to properly shutdown when ctrl+c'd (previously could swallow
  the interrupt due to cpython isinstance swallowing KeyboardInterrupt).


------------------------
pkgcore 0.1 (2006-09-30)
------------------------

- Initial release.

- Sync functionality doesn't yet exist (pmaint script will be in 0.2)

- pmerge vdb modification requires --force; this will be disabled in 0.2,
  mainly is in place so that folks who are just looking, don't inadvertantly
  trigger an actual modification.

- not all portage FEATURES are implemented; same for QA.

- If overlays are in use, pkgcore may defer to its' seperate cache to avoid
  pkgcore causing cache regen for portage (and vice versa); this occurs due
  to pkgcore treating overlays as their own repo and combining them at a
  higher level; portage smushes them all together thus rendering each subtree
  unusable in any standalone fashion.

- pkgcore is far more anal about blocking bad behaviour in ebuilds during
  metadata regeneration; tree is clean, but if you do something wrong in
  global scope, it *will* catch it and block it.

- EBD; daemonized ebuild.sh processing (effectively), pkgcore reuses old
  ebuild.sh processes to avoid bash startup, speeding regen up by roughly
  2x.
