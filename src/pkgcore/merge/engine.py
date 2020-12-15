"""
core engine for livefs modifications
"""

__all__ = ("alias_cset", "map_new_cset_livefs", "MergeEngine")

# need better documentation...

# pre merge triggers
# post merge triggers
# ordering?

import io
import operator
import tempfile
import traceback
from functools import partial
from itertools import chain
from multiprocessing import cpu_count

from snakeoil import data_source
from snakeoil.compatibility import IGNORED_EXCEPTIONS
from snakeoil.currying import post_curry
from snakeoil.fileutils import touch
from snakeoil.mappings import ImmutableDict, LazyValDict, StackedDict
from snakeoil.osutils import normpath

from ..fs import contents, livefs
from ..operations import observer as observer_mod
from ..plugin import get_plugins
from . import errors
from .const import INSTALL_MODE, REPLACE_MODE, UNINSTALL_MODE


def alias_cset(alias, engine, csets):
    """alias a cset to another"""
    return csets[alias]


def map_new_cset_livefs(engine, csets, cset_name='new_cset'):
    """Find symlinks on disk that redirect new_cset, and return a livefs localized cset."""
    initial = csets[cset_name]
    ondisk = contents.contentsSet(livefs.intersect(initial.iterdirs(), realpath=False))
    livefs.recursively_fill_syms(ondisk)
    ret = initial.map_directory_structure(ondisk, add_conflicting_sym=True)
    return ret


class MergeEngine:

    install_hooks = {x: [] for x in
        ("sanity_check", "pre_merge", "merge", "post_merge", "final")}
    uninstall_hooks = {x: [] for x in
        ("sanity_check", "pre_unmerge", "unmerge", "post_unmerge", "final")}
    replace_hooks = {x: [] for x in
        set(chain(install_hooks.keys(), uninstall_hooks.keys()))}

    install_csets = {
        "install_existing": "get_install_livefs_intersect",
        "resolved_install": map_new_cset_livefs,
        'new_cset': partial(alias_cset, 'raw_new_cset'),
        "install": partial(alias_cset, 'new_cset'),
        "replace": partial(alias_cset, 'new_cset'),
    }
    uninstall_csets = {
        "uninstall_existing": partial(alias_cset, "uninstall"),
        "uninstall": partial(alias_cset, "old_cset"),
        "old_cset": "get_uninstall_livefs_intersect",
    }
    replace_csets = install_csets.copy()
    replace_csets.update(uninstall_csets)
    replace_csets["modifying"] = (
        lambda e, c: c["resolved_install"].intersection(c["uninstall"]))
    replace_csets["uninstall"] = "get_remove_cset"
    replace_csets["replace"] = "get_replace_cset"
    replace_csets["install_existing"] = "get_install_livefs_intersect"

    install_csets_preserve = ["new_cset"]
    uninstall_csets_preserve = ["old_cset"]
    replace_csets_preserve = ["new_cset", "old_cset"]

    allow_reuse = True

    def __init__(self, mode, tempdir, hooks, csets, preserves, observer,
                 offset=None, disable_plugins=False, parallelism=None):
        if observer is None:
            observer = observer_mod.repo_observer(observer_mod.null_output)
        self.observer = observer
        self.mode = mode
        if tempdir is not None:
            tempdir = normpath(tempdir) + '/'
        self.tempdir = tempdir

        self.parallelism = parallelism if parallelism is not None else cpu_count()
        self.hooks = ImmutableDict((x, []) for x in hooks)

        self.preserve_csets = []
        self.cset_sources = {}
        # instantiate these separately so their values are preserved
        self.preserved_csets = LazyValDict(
            self.preserve_csets, self._get_cset_source)
        for k, v in csets.items():
            if isinstance(v, str):
                v = getattr(self, v, v)
            if not callable(v):
                raise TypeError(
                    "cset values must be either the string name of "
                    f"existing methods, or callables (got {v})")

            if k in preserves:
                self.add_preserved_cset(k, v)
            else:
                self.add_cset(k, v)

        if offset is None:
            offset = "/"
        self.offset = offset

        if not disable_plugins:
            # merge in default triggers first.
            for trigger in get_plugins('triggers'):
                t = trigger()
                t.register(self)

        # merge in overrides
        for hook, triggers in hooks.items():
            for trigger in triggers:
                self.add_trigger(hook, trigger)

        self.regenerate_csets()
        for x in hooks:
            setattr(self, x, partial(self.execute_hook, x))

    @classmethod
    def install(cls, tempdir, pkg, offset=None, observer=None,
                disable_plugins=False):
        """Generate a MergeEngine instance configured for installing a pkg.

        :param tempdir: tempspace for the merger to use; this space it must
            control alone, no sharing.
        :param pkg: :obj:`pkgcore.package.metadata.package` instance to install
        :param offset: any livefs offset to force for modifications
        :param disable_plugins: if enabled, run just the triggers passed in
        :return: :obj:`MergeEngine`
        """
        hooks = {k: [y() for y in v] for (k, v) in cls.install_hooks.items()}

        csets = cls.install_csets.copy()
        if "raw_new_cset" not in csets:
            csets["raw_new_cset"] = post_curry(cls.get_pkg_contents, pkg)
        o = cls(INSTALL_MODE, tempdir, hooks, csets, cls.install_csets_preserve,
                observer, offset=offset, disable_plugins=disable_plugins)

        if o.offset != '/':
            # wrap the results of new_cset to pass through an offset generator
            o.cset_sources["raw_new_cset"] = post_curry(
                o.generate_offset_cset, o.cset_sources["raw_new_cset"])

        o.new = pkg
        return o

    @classmethod
    def uninstall(cls, tempdir, pkg, offset=None, observer=None,
                  disable_plugins=False):
        """Generate a MergeEngine instance configured for uninstalling a pkg.

        :param tempdir: tempspace for the merger to use; this space it must
            control alone, no sharing.
        :param pkg: :obj:`pkgcore.package.metadata.package` instance to uninstall,
            must be from a livefs vdb
        :param offset: any livefs offset to force for modifications
        :param disable_plugins: if enabled, run just the triggers passed in
        :return: :obj:`MergeEngine`
        """
        hooks = {k: [y() for y in v] for (k, v) in cls.uninstall_hooks.items()}
        csets = cls.uninstall_csets.copy()

        if "raw_old_cset" not in csets:
            csets["raw_old_cset"] = post_curry(cls.get_pkg_contents, pkg)
        o = cls(UNINSTALL_MODE, tempdir, hooks, csets, cls.uninstall_csets_preserve,
                observer, offset=offset, disable_plugins=disable_plugins)

        if o.offset != '/':
            # wrap the results of new_cset to pass through an offset generator
            o.cset_sources["old_cset"] = post_curry(
                o.generate_offset_cset, o.cset_sources["old_cset"])

        o.old = pkg
        return o

    @classmethod
    def replace(cls, tempdir, old, new, offset=None, observer=None,
                disable_plugins=False):
        """Generate a MergeEngine instance configured for replacing a pkg.

        :param tempdir: tempspace for the merger to use; this space it must
            control alone, no sharing.
        :param old: :obj:`pkgcore.package.metadata.package` instance to replace,
            must be from a livefs vdb
        :param new: :obj:`pkgcore.package.metadata.package` instance
        :param offset: any livefs offset to force for modifications
        :param disable_plugins: if enabled, run just the triggers passed in
        :return: :obj:`MergeEngine`
        """
        hooks = {k: [y() for y in v] for (k, v) in cls.replace_hooks.items()}

        csets = cls.replace_csets.copy()

        csets.setdefault('raw_old_cset', post_curry(cls.get_pkg_contents, old))
        csets.setdefault('raw_new_cset', post_curry(cls.get_pkg_contents, new))

        o = cls(REPLACE_MODE, tempdir, hooks, csets, cls.replace_csets_preserve,
                observer, offset=offset, disable_plugins=disable_plugins)

        if o.offset != '/':
            for k in ("raw_old_cset", "raw_new_cset"):
                # wrap the results of new_cset to pass through an
                # offset generator
                o.cset_sources[k] = post_curry(
                    o.generate_offset_cset, o.cset_sources[k])

        o.old = old
        o.new = new
        return o

    def replace_cset(self, name, new_cset):
        """Replace the cset referenced by this engine.

        Use only if you know what you're doing.

        :param name: name of the cset
        :new_cset: a contentsSet instance to use
        """
        if name in self.preserved_csets:
            # yes this is evil awareness of LazyValDict internals...
            self.preserved_csets._vals[name] = new_cset
        else:
            raise KeyError(f"attempted to replace a non preserved cset: {name}")

    def regenerate_csets(self):
        """Internal function, reset non preserverd csets.

        Used in transitioning between hook points
        """
        self.csets = StackedDict(self.preserved_csets,
            LazyValDict(self.cset_sources, self._get_cset_source))

    def _get_cset_source(self, key):
        return self.cset_sources[key](self, self.csets)

    def add_preserved_cset(self, cset_name, func):
        """Register a cset generator for use.

        The cset will stay in memory until the engine finishes all steps.

        :param cset_name: what to call the generated cset
        :param func: callable to get the cset
        """
        self.add_cset(cset_name, func)
        self.preserve_csets.append(cset_name)

    def add_cset(self, cset_name, func):
        """Regiser a cset generator for use.

        The cset will be released from memory when it's no longer used.

        :param cset_name: what to call the generated cset
        :param func: callable to get the cset
        """
        if not callable(func):
            raise TypeError("func must be a callable")
        if not isinstance(cset_name, str):
            raise TypeError("cset_name must be a string")
        self.cset_sources[cset_name] = func

    def add_trigger(self, hook_name, trigger, required_csets):
        """Register a :obj:`pkgcore.merge.triggers.base` instance to be executed.

        :param hook_name: engine step to hook the trigger into
        :param trigger: :class:`pkgcore.merge.triggers.base` to add
        """
        if hook_name not in self.hooks:
            raise KeyError(
                f"trigger {trigger!r}'s hook {hook_name} isn't a known hook")

        if required_csets is not None:
            for rcs in required_csets:
                if rcs not in self.cset_sources:
                    if isinstance(rcs, str):
                        raise errors.TriggerUnknownCset(trigger, rcs)

        self.hooks[hook_name].append(trigger)

    def execute_hook(self, hook):
        """Execute any triggers bound to a hook point."""
        try:
            self.phase = hook
            self.regenerate_csets()
            for trigger in sorted(self.hooks[hook], key=operator.attrgetter("priority")):
                # error checking needed here.
                self.observer.trigger_start(hook, trigger)
                try:
                    try:
                        trigger(self, self.csets)
                    except IGNORED_EXCEPTIONS:
                        raise
                    except errors.BlockModification as e:
                        self.observer.error(
                            f"modification was blocked by trigger {trigger!r}: {e}")
                        raise
                    except errors.ModificationError as e:
                        self.observer.error(
                            f"modification error occurred during trigger {trigger!r}: {e}")
                        raise
                    except Exception as e:
                        if not trigger.suppress_exceptions:
                            raise

                        handle = io.StringIO()
                        traceback.print_exc(file=handle)

                        self.observer.warn(
                            "unhandled exception caught and "
                            f"suppressed:\n{handle.getvalue()}"
                        )
                finally:
                    self.observer.trigger_end(hook, trigger)
        finally:
            self.phase = None

    @staticmethod
    def generate_offset_cset(engine, csets, cset_generator):
        """Generate a cset with offset applied."""
        return cset_generator(engine, csets).insert_offset(engine.offset)

    @staticmethod
    def get_pkg_contents(engine, csets, pkg):
        """Generate the cset of what files shall be merged to the livefs."""
        return pkg.contents.clone()

    @staticmethod
    def get_remove_cset(engine, csets):
        """Generate the cset of what files shall be removed from the livefs."""
        return csets["old_cset"].difference(csets["install"])

    @staticmethod
    def get_replace_cset(engine, csets):
        """Return the cset of what will be replaced going from old->new pkg."""
        return csets["install"].intersection(csets["old_cset"])

    @staticmethod
    def _get_livefs_intersect_cset(engine, csets, cset_name, realpath=False):
        """Generate the livefs intersection against a cset."""
        return contents.contentsSet(livefs.intersect(csets[cset_name], realpath=realpath))

    @staticmethod
    def get_install_livefs_intersect(engine, csets):
        return engine._get_livefs_intersect_cset(engine, csets, "install")

    @staticmethod
    def get_uninstall_livefs_intersect(engine, csets):
        return engine._get_livefs_intersect_cset(engine, csets, "raw_old_cset")

    alias_cset = staticmethod(alias_cset)

    def get_merged_cset(self, strip_offset=True):
        cset = self.csets["install"]
        if self.offset not in (None, '/') and strip_offset:
            rewrite = contents.change_offset_rewriter(self.offset, '/', cset)
            cset = contents.contentsSet(rewrite)
        return cset

    def get_writable_fsobj(self, fsobj, prefer_reuse=True, empty=False):
        path = source = None
        if fsobj:
            source = fsobj.data
            if source.mutable:
                return fsobj
            if self.allow_reuse and prefer_reuse:
                path = source.path

                # XXX: this should be doing abspath fs intersection probably,
                # although the paths generated are from triggers/engine- still.

                if path is not None and not path.startswith(self.tempdir):
                    # the fsobj pathway isn't in temp space; force a transfer.
                    path = None

            if path:
                # ok, it's tempspace, and reusable.
                obj = data_source.local_source(path, True, encoding=source.encoding)

                if empty:
                    obj.bytes_fileobj(True).truncate(0)
                return obj

        # clone it into tempspace; it's required we control the tempspace,
        # so this function is safe in our usage.
        fd, path = tempfile.mkstemp(prefix='merge-engine-', dir=self.tempdir)

        # XXX: annoying quirk of python, we don't want append mode, so 'a+'
        # isn't viable; wr will truncate the file, so data_source uses r+.
        # this however doesn't allow us to state "create if missing"
        # so we create it ourselves. Annoying, but so it goes.
        # just touch the filepath.
        touch(path)
        new_source = data_source.local_source(
            path, True, encoding=getattr(fsobj, 'encoding', None))

        if source and not empty:
            data_source.transfer(source.bytes_fsobj(), new_source.bytes_fsobj(True))
        return new_source
