# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""make.conf translator.

Converts portage configuration files into L{pkgcore.config} form.
"""

import os
import stat
from pkgcore.config import basics, configurable
from pkgcore import const
from pkgcore.ebuild import const as ebuild_const
from pkgcore.util.osutils import (normpath, abspath, listdir_files,
    join as pjoin)
from pkgcore.util.demandload import demandload
demandload(globals(), "errno pkgcore.config:errors "
    "pkgcore.pkgsets.glsa:SecurityUpgrades "
    "pkgcore.util.file:read_bash_dict "
    "pkgcore.util:bzip2 "
    "pkgcore.log:logger ")


def my_convert_hybrid(manager, val, arg_type):
    """Modified convert_hybrid using a sequence of strings for section_refs."""
    subtype = None
    if arg_type == 'section_refs':
        subtype = 'section_ref'
    elif arg_type.startswith('refs:'):
        subtype = 'ref:' + arg_type.split(':', 1)[1]
    if subtype is not None:
        return list(
            basics.LazyNamedSectionRef(manager, subtype, name)
            for name in val)
    return basics.convert_hybrid(manager, val, arg_type)


@configurable({'ebuild_repo': 'ref:repo', 'vdb': 'ref:repo',
               'profile': 'ref:profile'}, typename='pkgset')
def SecurityUpgradesViaProfile(ebuild_repo, vdb, profile):
    """
    generate a GLSA vuln. pkgset limited by profile

    @param ebuild_repo: L{pkgcore.ebuild.repository.UnconfiguredTree} instance
    @param vdb: L{pkgcore.repository.prototype.tree} instance that is the livefs
    @param profile: L{pkgcore.ebuild.profiles} instance
    """
    arch = profile.arch
    if arch is None:
        raise errors.InstantiationError("arch wasn't set in profiles")
    return SecurityUpgrades(ebuild_repo, vdb, arch)


def make_syncer(basedir, sync_uri, options):
    d = {'basedir': basedir, 'uri': sync_uri}
    if sync_uri.startswith('rsync'):
        d['extra_opts'] = []
        if 'RSYNC_TIMEOUT' in options:
            d['timeout'] = options.pop('RSYNC_TIMEOUT').strip()
        if 'RSYNC_EXCLUDEFROM' in options:
            opts.extend('--exclude-from=%s' % x
                for x in options.pop('RSYNC_EXCLUDEFROM').split())
        if 'RSYNC_RETRIES' in options:
            d['retries'] = options.pop('RSYNC_RETRIES').strip()
        if 'PORTAGE_RSYNC_RETRIES' in options:
            d['retries'] = options.pop('PORTAGE_RSYNC_RETRIES').strip()
        if 'PORTAGE_RSYNC_EXTRA_OPTS' in options:
            d['extra_opts'].extend(
                options.pop('PORTAGE_RSYNC_EXTRA_OPTS').split())
        if 'RSYNC_RATELIMIT' in options:
            d['extra_opts'].append('--bwlimit=%s' %
                options.pop('RSYNC_RATELIMIT').strip())
        d['class'] = 'pkgcore.sync.rsync.rsync_timestamp_syncer'
    else:
        d['class'] = 'pkgcore.sync.base.GenericSyncer'
    return d

def add_sets(config, root, portage_base_dir):
    config["world"] = basics.AutoConfigSection({
            "class": "pkgcore.pkgsets.filelist.WorldFile",
            "location": pjoin(root, const.WORLD_FILE)})
    config["system"] = basics.AutoConfigSection({
            "class": "pkgcore.pkgsets.system.SystemSet",
            "profile": "profile"})
    config["installed"] = basics.AutoConfigSection({
            "class": "pkgcore.pkgsets.installed.Installed",
            "vdb": "vdb"})
    config["versioned-installed"] = basics.AutoConfigSection({
            "class": "pkgcore.pkgsets.installed.VersionedInstalled",
            "vdb": "vdb"})

    set_fp = pjoin(portage_base_dir, "sets")
    try:
        for setname in listdir_files(set_fp):
            # Potential for name clashes here, those will just make
            # the set not show up in config.
            if setname in ("system", "world"):
                logger.warn("user defined set %s is disallowed; ignoring" %
                    pjoin(set_fp, setname))
                continue
            new_config[setname] = basics.AutoConfigSection({
                    "class":"pkgcore.pkgsets.filelist.FileList",
                    "location":pjoin(set_fp, setname)})
    except OSError, e:
        if e.errno != errno.ENOENT:
            raise


def add_profile(config, base_path):
    make_profile = pjoin(base_path, 'make.profile')
    try:
        profile = normpath(abspath(pjoin(
                    base_path, os.readlink(make_profile))))
    except OSError, oe:
        if oe.errno in (errno.ENOENT, errno.EINVAL):
            raise errors.InstantiationError(
                "%s must be a symlink pointing to a real target" % (
                    make_profile,))
        raise errors.InstantiationError(
            "%s: unexepect error- %s" % (make_profile, oe.strerror))

    psplit = list(piece for piece in profile.split(os.path.sep) if piece)
    # poor mans rindex.
    try:
        profile_start = psplit.index('profiles')
    except ValueError:
        raise errors.InstantiationError(
            '%s expands to %s, but no profile detected' % (
                pjoin(base_path, 'make.profile'), profile))

    config["profile"] = basics.AutoConfigSection({
            "class": "pkgcore.ebuild.profiles.OnDiskProfile",
            "basepath": pjoin("/", *psplit[:-profile_start]),
            "profile": pjoin(*psplit[-profile_start:])})


def add_fetcher(config, conf_dict, distdir):
    fetchcommand = conf_dict.pop("FETCHCOMMAND")
    resumecommand = conf_dict.pop("RESUMECOMMAND", fetchcommand)

    # copy it to prevent modification.
    fetcher_dict = dict(conf_dict)
    # map a config arg to an obj arg, pop a few values
    if "FETCH_ATTEMPTS" in fetcher_dict:
        fetcher_dict["attempts"] = fetcher_dict.pop("FETCH_ATTEMPTS")
    fetcher_dict.pop("readonly", None)
    fetcher_dict.update(
        {"class": "pkgcore.fetch.custom.fetcher",
            "distdir": distdir,
            "command": fetchcommand,
            "resume_command": resumecommand
        })
    config["fetcher"] = basics.AutoConfigSection(fetcher_dict)



@configurable({'location': 'str'}, typename='configsection')
def config_from_make_conf(location="/etc/"):
    """
    generate a config from a file location

    @param location: location the portage configuration is based in,
        defaults to /etc
    """

    # this actually differs from portage parsing- we allow
    # make.globals to provide vars used in make.conf, portage keeps
    # them seperate (kind of annoying)

    config_root = os.environ.get("CONFIG_ROOT", "/")
    base_path = pjoin(config_root, location.strip("/"))
    portage_base = pjoin(base_path, "portage")

    # this isn't preserving incremental behaviour for features/use
    # unfortunately
    conf_dict = read_bash_dict(pjoin(base_path, "make.globals"))
    conf_dict.update(read_bash_dict(
            pjoin(base_path, "make.conf"), vars_dict=conf_dict,
            sourcing_command="source"))
    conf_dict.setdefault("PORTDIR", "/usr/portage")
    root = os.environ.get("ROOT", conf_dict.get("ROOT", "/"))
    gentoo_mirrors = list(
        x+"/distfiles" for x in conf_dict.pop("GENTOO_MIRRORS", "").split())
    if not gentoo_mirrors:
        gentoo_mirrors = None

    features = conf_dict.get("FEATURES", "").split()

    new_config = {}

    # sets...
    add_sets(new_config, root, portage_base)
    add_profile(new_config, base_path)

    kwds = {"class": "pkgcore.vdb.repository",
            "location": pjoin(config_root, 'var', 'db', 'pkg')}
    kwds["cache_location"] = pjoin(config_root, 'var', 'cache', 'edb', 
        'dep', 'var', 'db', 'pkg')
    new_config["vdb"] = basics.AutoConfigSection(kwds)
    
    portdir = normpath(conf_dict.pop("PORTDIR").strip())
    portdir_overlays = [
        normpath(x) for x in conf_dict.pop("PORTDIR_OVERLAY", "").split()]


    # define the eclasses now.
    all_ecs = []
    for x in [portdir] + portdir_overlays:
        ec_path = pjoin(x, "eclass")
        new_config[ec_path] = basics.AutoConfigSection({
                "class": "pkgcore.ebuild.eclass_cache.cache",
                "path": ec_path,
                "portdir": portdir})
        all_ecs.append(ec_path)

    new_config['ebuild-repo-common'] = basics.AutoConfigSection({
            'class': 'pkgcore.ebuild.repository.tree',
            'default_mirrors': gentoo_mirrors,
            'eclass_cache': 'eclass stack'})
    new_config['cache-common'] = basics.AutoConfigSection({
            'class': 'pkgcore.cache.flat_hash.database',
            'auxdbkeys': ebuild_const.metadata_keys,
            'location': pjoin(config_root, 'var', 'cache', 'edb', 'dep'),
            })

    for tree_loc in portdir_overlays:
        new_config[tree_loc] = basics.AutoConfigSection({
                'inherit': ('ebuild-repo-common',),
                'location': tree_loc,
                'cache': (basics.AutoConfigSection({
                            'inherit': ('cache-common',),
                            'label': tree_loc}),),
                'class': 'pkgcore.ebuild.repository.SlavedTree',
                'parent_repo': 'portdir'
                })

    rsync_portdir_cache = os.path.exists(pjoin(portdir, "metadata", "cache")) \
        and "metadata-transfer" not in features

    # if a metadata cache exists, use it
    if rsync_portdir_cache:
        new_config["portdir cache"] = basics.AutoConfigSection({
                'class': 'pkgcore.cache.metadata.database',
                'location': portdir,
                'label': 'portdir cache',
                'auxdbkeys': ebuild_const.metadata_keys})
    else:
        new_config["portdir cache"] = basics.AutoConfigSection({
                'inherit': ('cache-common',),
                'label': portdir})

    syncer = conf_dict.pop("SYNC", None)
    base_portdir_config = {}
    if syncer is not None:
        new_config["%s syncer" % portdir] = basics.AutoConfigSection(
            make_syncer(portdir, syncer, conf_dict))
        base_portdir_config = {"sync": "%s syncer" % portdir}

    # setup portdir.
    cache = ('portdir cache',)
    if not portdir_overlays:
        d = dict(base_portdir_config)
        d['inherit'] = ('ebuild-repo-common',)
        d['location'] = portdir
        d['cache'] = ('portdir cache',)

        new_config[portdir] = basics.DictConfigSection(my_convert_hybrid, d)
        new_config["eclass stack"] = basics.section_alias(
            pjoin(portdir, 'eclass'), 'eclass_cache')
        new_config['portdir'] = basics.section_alias(portdir, 'repo')
        new_config['repo-stack'] = basics.section_alias(portdir, 'repo')
    else:
        # There's always at least one (portdir) so this means len(all_ecs) > 1
        new_config['%s cache' % (portdir,)] = basics.AutoConfigSection({
                'inherit': ('cache-common',),
                'label': portdir})
        cache = ('portdir cache',)
        if rsync_portdir_cache:
            cache = ('%s cache' % (portdir,),) + cache

        d = dict(base_portdir_config)
        d['inherit'] = ('ebuild-repo-common',)
        d['location'] = portdir
        d['cache'] = cache

        new_config[portdir] = basics.DictConfigSection(my_convert_hybrid, d)

        if rsync_portdir_cache:
            # created higher up; two caches, writes to the local,
            # reads (when possible) from pregenned metadata
            cache = ('portdir cache',)
        else:
            cache = ('%s cache' % (portdir,),)
        new_config['portdir'] = basics.DictConfigSection(my_convert_hybrid, {
                'inherit': ('ebuild-repo-common',),
                'location': portdir,
                'cache': cache,
                'eclass_cache': pjoin(portdir, 'eclass')})

        # reverse the ordering so that overlays override portdir
        # (portage default)
        new_config["eclass stack"] = basics.DictConfigSection(
            my_convert_hybrid, {
                'class': 'pkgcore.ebuild.eclass_cache.StackedCaches',
                'eclassdir': pjoin(portdir, "eclass"),
                'caches': tuple(reversed(all_ecs))})

        new_config['repo-stack'] = basics.DictConfigSection(my_convert_hybrid,
            {'class': 'pkgcore.ebuild.overlay_repository.OverlayRepo',
             'trees': tuple(reversed([portdir] + portdir_overlays))})

    # disabled code for using portage config defined cache modules;
    # need to re-examine and see if they're still in sync with our cache subsystem
#     if os.path.exists(base_path+"portage/modules"):
#         pcache = read_dict(
#             base_path+"portage/modules").get("portdbapi.auxdbmodule", None)

#        cache_config = {"type": "cache",
#                        "location": "%s/var/cache/edb/dep" %
#                           config_root.rstrip("/"),
#                        "label": "make_conf_overlay_cache"}
#        if pcache is None:
#            if portdir_overlays or ("metadata-transfer" not in features):
#                cache_config["class"] = "pkgcore.cache.flat_hash.database"
#            else:
#                cache_config["class"] = "pkgcore.cache.metadata.database"
#                cache_config["location"] = portdir
#        	 cache_config["readonly"] = "true"
#        else:
#            cache_config["class"] = pcache
#
#        new_config["cache"] = basics.ConfigSectionFromStringDict(
#            "cache", cache_config)


    new_config['glsa'] = basics.AutoConfigSection({
            'class': SecurityUpgradesViaProfile,
            'ebuild_repo': 'repo-stack',
            'vdb': 'vdb',
            'profile': 'profile'})

    #binpkg.
    pkgdir = conf_dict.pop('PKGDIR', None)
    default_repos = ('repo-stack',)
    if pkgdir is not None:
        try:
            pkgdir = abspath(pkgdir)
        except OSError, oe:
            if oe.errno != errno.ENOENT:
                raise
            pkgdir = None
        # If we are not using the native bzip2 then the Tarfile.bz2open
        # the binpkg repository uses will fail.
        if pkgdir and os.path.isdir(pkgdir) and bzip2.native:
            new_config['binpkg'] = basics.ConfigSectionFromStringDict({
                    'class': 'pkgcore.binpkg.repository.tree',
                    'location': pkgdir})
            default_repos += ('binpkg',)

    # now add the fetcher- we delay it till here to clean out the environ
    # it passes to the command.
    # *everything* in the conf_dict must be str values also.
    distdir = normpath(conf_dict.pop("DISTDIR", pjoin(portdir, "distdir")))
    add_fetcher(new_config, conf_dict, distdir)

    # finally... domain.
    conf_dict.update({
            'class': 'pkgcore.ebuild.domain.domain',
            'repositories': default_repos,
            'fetcher': 'fetcher',
            'default': True,
            'vdb': ('vdb',),
            'profile': 'profile',
            'name': 'livefs domain'})
    for f in (
        "package.mask", "package.unmask", "package.keywords", "package.use",
            "bashrc"):
        fp = pjoin(portage_base, f)
        try:
            st = os.stat(fp)
        except OSError, oe:
            if oe.errno != errno.ENOENT:
                raise
        else:
            if stat.S_ISREG(st.st_mode):
                conf_dict[f] = fp
            elif stat.S_ISDIR(st.st_mode):
                conf_dict[f + '-dirs'] = fp

    new_config['livefs domain'] = basics.DictConfigSection(my_convert_hybrid,
                                                           conf_dict)

    return new_config
