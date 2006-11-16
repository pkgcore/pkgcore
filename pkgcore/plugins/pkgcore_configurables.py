# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2

from pkgcore.config import basics
from pkgcore.ebuild import (
    portage_conf, repository as ebuild_repo, profiles, domain, eclass_cache,
    overlay_repository)
from pkgcore.pkgsets import system, filelist, installed, glsa
from pkgcore.vdb import ondisk
from pkgcore.cache import flat_hash, metadata
from pkgcore.fetch import custom
from pkgcore.binpkg import repository as binpkg_repo


pkgcore_plugins = {
    'configurable': [
        basics.section_alias,
        basics.parse_config_file,
        portage_conf.SecurityUpgradesViaProfile,
        portage_conf.config_from_make_conf,
        system.SystemSet,
        ondisk.tree,
        flat_hash.database,
        metadata.database,
        metadata.paludis_flat_list,
        custom.fetcher,
        binpkg_repo.tree,
        ebuild_repo.UnconfiguredTree,
        profiles.OnDiskProfile,
        domain.domain,
        eclass_cache.cache,
        eclass_cache.StackedCaches,
        overlay_repository.OverlayRepo,
        filelist.FileList,
        filelist.WorldFile,
        installed.Installed,
        installed.VersionedInstalled,
        glsa.GlsaDirSet,
        glsa.SecurityUpgrades,
        ],
    }
