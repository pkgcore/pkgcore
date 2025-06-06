"""gentoo/ebuild specific triggers"""

__all__ = (
    "collapse_envd",
    "string_collapse_envd",
    "env_update",
    "ConfigProtectInstall",
    "ConfigProtectUninstall",
    "preinst_contents_reset",
    "CollisionProtect",
    "ProtectOwned",
    "install_into_symdir_protect",
    "InfoRegen",
    "SFPerms",
    "FixImageSymlinks",
    "GenerateTriggers",
)

import fnmatch
import os

from snakeoil.bash import read_bash_dict
from snakeoil.fileutils import AtomicWriteFile
from snakeoil.osutils import listdir_files, normpath, pjoin
from snakeoil.sequences import iflatten_instance, stable_unique

from .. import os_data
from ..fs import livefs
from ..merge import const, errors, triggers
from ..restrictions import values
from ..system import libtool

colon_parsed = frozenset(
    [
        "ADA_INCLUDE_PATH",
        "ADA_OBJECTS_PATH",
        "INFODIR",
        "INFOPATH",
        "LDPATH",
        "MANPATH",
        "PATH",
        "PYTHONPATH",
        "PKG_CONFIG_PATH",
        "ROOTPATH",
    ]
)

incrementals = frozenset(
    [
        "ADA_INCLUDE_PATH",
        "ADA_OBJECTS_PATH",
        "CLASSPATH",
        "CONFIG_PROTECT",
        "CONFIG_PROTECT_MASK",
        "INFODIR",
        "INFOPATH",
        "KDEDIRS",
        "LDPATH",
        "MANPATH",
        "PATH",
        "PYTHONPATH",
        "ROOTPATH",
        "PKG_CONFIG_PATH",
    ]
)


def collapse_envd(base):
    collapsed_d = {}
    try:
        env_d_files = sorted(listdir_files(base))
    except FileNotFoundError:
        pass
    else:
        for x in env_d_files:
            if (
                x.endswith(".bak")
                or x.endswith("~")
                or x.startswith("._cfg")
                or len(x) <= 2
                or not x[0:2].isdigit()
            ):
                continue
            d = read_bash_dict(pjoin(base, x))
            # inefficient, but works.
            for k, v in d.items():
                collapsed_d.setdefault(k, []).append(v)
            del d

    loc_incrementals = set(incrementals)
    loc_colon_parsed = set(colon_parsed)

    # split out env.d defined incrementals..
    # update incrementals *and* colon parsed for colon_separated;
    # incrementals on its own is space separated.

    for x in collapsed_d.pop("COLON_SEPARATED", []):
        v = x.split()
        if v:
            loc_colon_parsed.update(v)

    loc_incrementals.update(loc_colon_parsed)

    # now space.
    for x in collapsed_d.pop("SPACE_SEPARATED", []):
        v = x.split()
        if v:
            loc_incrementals.update(v)

    # now reinterpret.
    for k, v in collapsed_d.items():
        if k not in loc_incrementals:
            collapsed_d[k] = v[-1]
            continue
        if k in loc_colon_parsed:
            collapsed_d[k] = [
                _f for _f in iflatten_instance(x.split(":") for x in v) if _f
            ]
        else:
            collapsed_d[k] = [
                _f for _f in iflatten_instance(x.split() for x in v) if _f
            ]

    return collapsed_d, loc_incrementals, loc_colon_parsed


def string_collapse_envd(envd_dict, incrementals, colon_incrementals):
    """transform a passed in dict to strictly strings"""
    for k, v in envd_dict.items():
        if k not in incrementals:
            continue
        if k in colon_incrementals:
            envd_dict[k] = ":".join(v)
        else:
            envd_dict[k] = " ".join(v)


def update_ldso(ld_search_path, offset="/"):
    # we do an atomic rename instead of open and write quick
    # enough (avoid the race iow)
    fp = pjoin(offset, "etc", "ld.so.conf")
    new_f = AtomicWriteFile(fp, uid=os_data.root_uid, gid=os_data.root_uid, perms=0o644)
    new_f.write("# automatically generated, edit env.d files instead\n")
    new_f.writelines(x.strip() + "\n" for x in ld_search_path)
    new_f.close()


def perform_env_update(root, skip_ldso_update=False):
    d, inc, colon = collapse_envd(pjoin(root, "etc/env.d"))

    l = d.pop("LDPATH", None)
    if l is not None and not skip_ldso_update:
        update_ldso(l, root)

    string_collapse_envd(d, inc, colon)

    new_f = AtomicWriteFile(
        pjoin(root, "etc", "profile.env"),
        uid=os_data.root_uid,
        gid=os_data.root_gid,
        perms=0o644,
    )
    new_f.write("# autogenerated.  update env.d instead\n")
    new_f.writelines(f'export {k}="{d[k]}"\n' for k in sorted(d))
    new_f.close()
    new_f = AtomicWriteFile(
        pjoin(root, "etc", "profile.csh"),
        uid=os_data.root_uid,
        gid=os_data.root_gid,
        perms=0o644,
    )
    new_f.write("# autogenerated, update env.d instead\n")
    new_f.writelines(f'setenv {k}="{d[k]}"\n' for k in sorted(d))
    new_f.close()


class env_update(triggers.base):
    required_csets = ()
    priority = 5
    _hooks = ("post_unmerge", "post_merge")

    def trigger(self, engine):
        perform_env_update(engine.offset)


def simple_chksum_compare(x, y):
    found = False
    for k, v in x.chksums.items():
        if k == "size":
            continue
        o = y.chksums.get(k)
        if o is not None:
            if o != v:
                return False
            found = True
    if "size" in x.chksums and "size" in y.chksums:
        return x.chksums["size"] == y.chksums["size"]
    return found


def gen_config_protect_filter(offset, extra_protects=(), extra_disables=()):
    collapsed_d, inc, colon = collapse_envd(pjoin(offset, "etc/env.d"))
    collapsed_d.setdefault("CONFIG_PROTECT", []).extend(extra_protects)
    collapsed_d.setdefault("CONFIG_PROTECT_MASK", []).extend(extra_disables)

    r = [
        values.StrGlobMatch(normpath(x).rstrip("/") + "/")
        for x in set(stable_unique(collapsed_d["CONFIG_PROTECT"] + ["/etc"]))
    ]
    if len(r) > 1:
        r = values.OrRestriction(*r)
    else:
        r = r[0]
    neg = stable_unique(collapsed_d["CONFIG_PROTECT_MASK"])
    if neg:
        if len(neg) == 1:
            r2 = values.StrGlobMatch(normpath(neg[0]).rstrip("/") + "/", negate=True)
        else:
            r2 = values.OrRestriction(
                negate=True,
                *[values.StrGlobMatch(normpath(x).rstrip("/") + "/") for x in set(neg)],
            )
        r = values.AndRestriction(r, r2)
    return r


def gen_collision_ignore_filter(offset, extra_ignores=()):
    collapsed_d, inc, colon = collapse_envd(pjoin(offset, "etc/env.d"))
    ignored = collapsed_d.setdefault("COLLISION_IGNORE", [])
    ignored.extend(extra_ignores)
    ignored.extend(["*/.keep", "*/.keep_*"])

    ignored = stable_unique(ignored)
    for i, x in enumerate(ignored):
        if not x.endswith("/*") and os.path.isdir(x):
            ignored[i] = ignored.rstrip("/") + "/*"
    ignored = [values.StrRegex(fnmatch.translate(x)) for x in stable_unique(ignored)]
    if len(ignored) == 1:
        return ignored[0]
    return values.OrRestriction(*ignored)


class ConfigProtectInstall(triggers.base):
    required_csets = ("install_existing", "install")
    priority = 100
    _hooks = ("pre_merge",)

    def __init__(self, extra_protects=(), extra_disables=()):
        super().__init__()
        self.renames = {}
        self.extra_protects = extra_protects
        self.extra_disables = extra_disables

    def register(self, engine):
        super().register(engine)
        t2 = ConfigProtectInstall_restore(self.renames)
        t2.register(engine)

    def trigger(self, engine, existing_cset, install_cset):
        # hackish, but it works.
        protected_filter = gen_config_protect_filter(
            engine.offset, self.extra_protects, self.extra_disables
        ).match
        ignore_filter = gen_collision_ignore_filter(engine.offset).match
        protected = {}

        for x in existing_cset.iterfiles():
            if not ignore_filter(x.location) and protected_filter(x.location):
                replacement = install_cset[x]
                if not simple_chksum_compare(replacement, x):
                    protected.setdefault(
                        pjoin(
                            engine.offset,
                            os.path.dirname(x.location).lstrip(os.path.sep),
                        ),
                        [],
                    ).append((os.path.basename(replacement.location), replacement))

        for dir_loc, entries in protected.items():
            updates = {x[0]: [] for x in entries}
            try:
                existing = sorted(
                    x for x in listdir_files(dir_loc) if x.startswith("._cfg")
                )
            except FileNotFoundError:
                # this shouldn't occur.
                continue

            for x in existing:
                try:
                    # ._cfg0000_filename
                    count = int(x[5:9])
                    if x[9] != "_":
                        raise ValueError
                    fn = x[10:]
                except (ValueError, IndexError):
                    continue
                if fn in updates:
                    updates[fn].append((count, fn))

            # now we rename.
            for fname, entry in entries:
                # check for any updates with the same chksums.
                count = 0
                for cfg_count, cfg_fname in updates[fname]:
                    if simple_chksum_compare(
                        livefs.gen_obj(pjoin(dir_loc, cfg_fname)), entry
                    ):
                        count = cfg_count
                        break
                    count = max(count, cfg_count + 1)
                try:
                    install_cset.remove(entry)
                except KeyError:
                    # this shouldn't occur...
                    continue
                new_fn = pjoin(dir_loc, "._cfg%04i_%s" % (count, fname))
                new_entry = entry.change_attributes(location=new_fn)
                install_cset.add(new_entry)
                self.renames[new_entry] = entry
            del updates


class ConfigProtectInstall_restore(triggers.base):
    required_csets = ("install",)
    priority = 10
    _hooks = ("post_merge",)

    def __init__(self, renames_dict):
        super().__init__()
        self.renames = renames_dict

    def trigger(self, engine, install_cset):
        for new_entry, old_entry in self.renames.items():
            try:
                install_cset.remove(new_entry)
            except KeyError:
                continue
            install_cset.add(old_entry)
        self.renames.clear()


class ConfigProtectUninstall(triggers.base):
    required_csets = ("uninstall_existing", "uninstall")
    _hooks = ("pre_unmerge",)

    def trigger(self, engine, existing_cset, uninstall_cset):
        protected_filter = gen_config_protect_filter(engine.offset).match
        ignore_filter = gen_collision_ignore_filter(engine.offset).match

        remove = []
        for x in existing_cset.iterfiles():
            if not ignore_filter(x.location) and protected_filter(x.location):
                recorded_ent = uninstall_cset[x]
                try:
                    if not simple_chksum_compare(recorded_ent, x):
                        # chksum differs.  file stays.
                        remove.append(recorded_ent)
                # If a file doesn't exist we don't need to remove it
                except (FileNotFoundError, NotADirectoryError):
                    pass

        for x in remove:
            del uninstall_cset[x]


class UninstallIgnore(triggers.base):
    required_csets = {
        const.REPLACE_MODE: ("uninstall_existing", "uninstall", "old_cset"),
        const.UNINSTALL_MODE: ("uninstall_existing", "uninstall"),
    }

    _hooks = ("pre_unmerge",)
    _engine_types = triggers.UNINSTALLING_MODES

    def __init__(self, uninstall_ignore=()):
        super().__init__()
        self.uninstall_ignore = uninstall_ignore

    def trigger(self, engine, existing_cset, uninstall_cset, old_cset={}):
        ignore = [
            values.StrRegex(fnmatch.translate(x), match=True)
            for x in self.uninstall_ignore
        ]
        ignore_filter = values.OrRestriction(*ignore).match

        remove = [x for x in existing_cset.iterfiles() if ignore_filter(x.location)]
        for x in remove:
            # don't remove matching files being uninstalled
            del uninstall_cset[x]
            # don't remove matching files being replaced
            old_cset.discard(x)


class preinst_contents_reset(triggers.base):
    required_csets = ("new_cset",)
    priority = 1
    _hooks = ("pre_merge",)

    def __init__(self, format_op):
        super().__init__()
        self.format_op = format_op

    def trigger(self, engine, cset):
        # wipe, and get data again; ebuild preinst does untrackable
        # modifications to the fs
        cset.clear()
        cs = engine.new._parent.scan_contents(self.format_op.env["D"])
        if engine.offset != "/":
            cs = cs.insert_offset(engine.offset)
        cset.update(cs)


class FileCollision(triggers.base):
    """Generic livefs file collision trigger."""

    required_csets = {
        const.INSTALL_MODE: ("install", "install_existing"),
        const.REPLACE_MODE: ("install", "install_existing", "old_cset"),
    }

    _hooks = ("sanity_check",)
    _engine_types = triggers.INSTALLING_MODES

    suppress_exceptions = False

    def __init__(self, extra_protects=(), extra_disables=(), extra_ignores=()):
        super().__init__()
        self.extra_protects = extra_protects
        self.extra_disables = extra_disables
        self.extra_ignores = extra_ignores

    def collision(self, colliding):
        """Handle livefs file collisions.

        Must be overridden in derived trigger classes.
        """
        raise NotImplementedError

    def trigger(self, engine, install, existing, old_cset=()):
        if not existing:
            return

        # for the moment, we just care about files
        colliding = existing.difference(install.iterdirs())

        # hackish, but it works.
        protected_filter = gen_config_protect_filter(
            engine.offset, self.extra_protects, self.extra_disables
        ).match
        ignore_filter = gen_collision_ignore_filter(
            engine.offset, self.extra_ignores
        ).match

        ignores = []
        for x in colliding:
            if protected_filter(x.location) or ignore_filter(x.location):
                ignores.append(x)

        colliding.difference_update(ignores)
        if not colliding:
            return

        # Wipe the references since we may throw an exception- we don't want
        # potentially millions of references being kept in memory for heavy
        # ignore matches.
        del ignores, protected_filter, ignore_filter
        colliding.difference_update(old_cset)

        if colliding:
            self.collision(colliding)


class CollisionProtect(FileCollision):
    def collision(self, colliding):
        raise errors.BlockModification(
            self,
            "collision-protect: file(s) already exist: ( %s )"
            % ", ".join(repr(x) for x in sorted(colliding)),
        )


class ProtectOwned(FileCollision):
    def __init__(self, vdb, *args):
        super().__init__(*args)
        self.vdb = vdb

    def collision(self, colliding):
        real_pkgs = (pkg for repo in self.vdb for pkg in repo if pkg.package_is_real)
        collisions = {}

        # TODO: worth parallelizing this vdb scanning?
        for pkg in real_pkgs:
            pkg_file_collisions = pkg.contents.intersection(colliding)
            if pkg_file_collisions:
                collisions[pkg.cpvstr] = pkg_file_collisions

        if collisions:
            pkg_collisions = [
                "( %s ) owned by '%s'"
                % (
                    ", ".join(repr(x) for x in sorted(collisions[pkg_cpvstr])),
                    pkg_cpvstr,
                )
                for pkg_cpvstr in sorted(collisions.keys())
            ]
            raise errors.BlockModification(
                self, "protect-owned: %s" % (", ".join(pkg_collisions),)
            )

        # TODO: output a file override warning here


class install_into_symdir_protect(triggers.base):
    required_csets = {
        const.INSTALL_MODE: ("install", "install_existing"),
        const.REPLACE_MODE: ("install", "install_existing", "old_cset"),
    }

    _hooks = ("sanity_check",)
    _engine_types = triggers.INSTALLING_MODES

    def __init__(self, extra_protects=(), extra_disables=()):
        super().__init__()
        self.extra_protects = extra_protects
        self.extra_disables = extra_disables

    def trigger(self, engine, install, existing, old_cset=()):
        return
        if not existing:
            return

        # avoid generator madness
        install_into_symdir = []
        for linkset in [install.iterlinks(), existing.iterlinks()]:
            linkset = list(linkset)
            if linkset:
                for inst_file in install.iterfiles():
                    for sym in linkset:
                        if inst_file.location.startswith(sym.location + "/"):
                            install_into_symdir.append(inst_file)

        if install_into_symdir:
            raise errors.BlockModification(
                self,
                "file(s) installed into symlinked dir, will break when "
                "removing files from the original dir: ( %s )"
                % ", ".join(repr(x) for x in sorted(install_into_symdir)),
            )


class InfoRegen(triggers.InfoRegen):
    _label = "ebuild info regen"

    def register(self, engine):
        # wipe pre-existing info triggers.
        for x in self._hooks:
            if x not in engine.hooks:
                continue
            # yucky, but works.
            wipes = [y for y in engine.hooks[x] if y.label == triggers.InfoRegen._label]
            for y in wipes:
                engine.hooks[x].remove(y)
        triggers.InfoRegen.register(self, engine)

    def should_skip_directory(self, basepath, files):
        return any(x.startswith(".keepinfodir") for x in files)

    def trigger(self, engine, *args):
        self.engine = engine
        self.path = pjoin(engine.offset, "etc/env.d")
        triggers.InfoRegen.trigger(self, engine, *args)

    @property
    def locations(self):
        collapsed_d = collapse_envd(self.path)[0]
        l = collapsed_d.get("INFOPATH", ())
        if not l:
            return triggers.InfoRegen.locations
        elif isinstance(l, str):
            l = l.split()
        return l


class SFPerms(triggers.base):
    required_csets = ("new_cset",)
    _hooks = ("pre_merge",)
    _engine_types = triggers.INSTALLING_MODES

    def trigger(self, engine, cset):
        resets = []
        for x in cset.iterfiles():
            if x.mode & 0o4000:
                if x.mode & 0o044:
                    engine.observer.warn(
                        f"sfperms: dropping group/world read due to SetGID: {x!r}"
                    )
                    resets.append(x.change_attributes(mode=x.mode & ~0o44))
            if x.mode & 0o2000:
                if x.mode & 0o004:
                    engine.observer.warn(
                        f"sfperms: dropping world read due to SetUID: {x!r}"
                    )
                    resets.append(x.change_attributes(mode=x.mode & ~0o04))
        cset.update(resets)


def register_multilib_strict_trigger(opts):
    locations = opts.get("MULTILIB_STRICT_DIRS")
    exempt = opts.get("MULTILIB_STRICT_EXEMPT", "(perl5|gcc|gcc-lib)")
    deny_pattern = opts.get("MULTILIB_STRICT_DENY")
    if None in (locations, deny_pattern):
        return
    locations = locations.split()
    if not locations:
        return
    elif len(locations) == 1:
        locations = locations[0]
    else:
        locations = f"({'|'.join(locations)})"
    limit_pattern = f"/{locations}/(?!{exempt})"
    while "//" in limit_pattern:
        limit_pattern = limit_pattern.replace("//", "/")
    # this seems semi dodgey, specifically, that it won't catch 'em all
    trig = triggers.BlockFileType(f".*{deny_pattern}.*", limit_pattern)
    return trig


class FixImageSymlinks(triggers.base):
    required_csets = ("new_cset",)
    _hooks = ("pre_merge",)

    def __init__(self, format_op):
        super().__init__()
        self.format_op = format_op

    def trigger(self, engine, cset):
        d = self.format_op.env["D"].rstrip("/") + "/"
        l = [x for x in cset.iterlinks() if x.target.startswith(d)]
        if engine.observer:
            o = engine.observer
            for x in l:
                o.warn(f"correcting {x.location} sym pointing into $D: {x.target}")
        d_len = len(d)

        # drop the leading ${D}, and force an abspath via '/'
        cset.update(x.change_attributes(target=pjoin("/", x.target[d_len:])) for x in l)


class GenerateTriggers:
    def __init__(self, domain, settings):
        self.domain = domain
        self.opts = {}

        # Pop trigger-related options from the system config, they shouldn't be
        # needed anywhere else and doing so prevents them from leaking into the
        # ebuild env.

        config_lists = (
            "CONFIG_PROTECT",
            "CONFIG_PROTECT_MASK",
            "COLLISION_IGNORE",
            "INSTALL_MASK",
            "UNINSTALL_IGNORE",
        )
        for x in config_lists:
            self.opts[x] = settings.pop(x, [])
            if isinstance(self.opts[x], str):
                self.opts[x] = self.opts[x].split()

        config_opts = (
            "PKGDIR",
            "MULTILIB_STRICT_DIRS",
            "MULTILIB_STRICT_EXEMPT",
            "MULTILIB_STRICT_DENY",
            "DEB_REPO_ROOT",
            "DEB_MAINAINER",
            "DEB_ARCHITECTURE",
        )
        for x in config_opts:
            self.opts[x] = settings.pop(x, None)

    def __iter__(self):
        yield env_update()

        yield ConfigProtectInstall(
            self.opts["CONFIG_PROTECT"], self.opts["CONFIG_PROTECT_MASK"]
        )
        yield ConfigProtectUninstall()

        if "collision-protect" in self.domain.features:
            yield CollisionProtect(
                self.opts["CONFIG_PROTECT"],
                self.opts["CONFIG_PROTECT_MASK"],
                self.opts["COLLISION_IGNORE"],
            )

        if (
            "protect-owned" in self.domain.features
            and "collision-protect" not in self.domain.features
        ):
            yield ProtectOwned(
                self.domain.installed_repos,
                self.opts["CONFIG_PROTECT"],
                self.opts["CONFIG_PROTECT_MASK"],
                self.opts["COLLISION_IGNORE"],
            )

        if "multilib-strict" in self.domain.features:
            yield register_multilib_strict_trigger(self.opts)

        if "sfperms" in self.domain.features:
            yield SFPerms()

        yield install_into_symdir_protect(
            self.opts["CONFIG_PROTECT"], self.opts["CONFIG_PROTECT_MASK"]
        )

        # TODO: support multiple binpkg repo targets?
        pkgdir = self.opts.get("PKGDIR", None)
        if pkgdir:
            target_repo = self.domain.binary_repos_raw.get(pkgdir, None)
        else:
            # get the highest priority binpkg repo
            try:
                target_repo = self.domain.binary_repos_raw[0]
            except IndexError:
                target_repo = None
        if target_repo is not None:
            if "buildpkg" in self.domain.features:
                yield triggers.SavePkg(pristine="no", target_repo=target_repo)
            elif "pristine-buildpkg" in self.domain.features:
                yield triggers.SavePkg(pristine="yes", target_repo=target_repo)
            elif "buildsyspkg" in self.domain.features:
                yield triggers.SavePkgIfInPkgset(
                    pristine="yes",
                    target_repo=target_repo,
                    pkgset=self.domain.profile.system,
                )
            elif "unmerge-backup" in self.domain.features:
                yield triggers.SavePkgUnmerging(target_repo=target_repo)

        if "splitdebug" in self.domain.features:
            yield triggers.BinaryDebug(
                mode="split", compress=("compressdebug" in self.domain.features)
            )
        elif "strip" in self.domain.features or "nostrip" not in self.domain.features:
            yield triggers.BinaryDebug(mode="strip")

        if "-fixlafiles" not in self.domain.features:
            yield libtool.FixLibtoolArchivesTrigger()

        for x in ("man", "info", "doc"):
            if f"no{x}" in self.domain.features:
                self.opts["INSTALL_MASK"].append(f"/usr/share/{x}")
        l = []
        for x in self.opts["INSTALL_MASK"]:
            x = x.rstrip("/")
            l.append(values.StrRegex(fnmatch.translate(x)))
            l.append(values.StrRegex(fnmatch.translate(f"{x}/*")))
        install_mask = l

        if install_mask:
            if len(install_mask) == 1:
                install_mask = install_mask[0]
            else:
                install_mask = values.OrRestriction(*install_mask)
            yield triggers.PruneFiles(install_mask.match)
            # note that if this wipes all /usr/share/ entries, should
            # wipe the empty dir.

        yield UninstallIgnore(self.opts["UNINSTALL_IGNORE"])
        yield InfoRegen()
