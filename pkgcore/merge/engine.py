# Copyright: 2005-2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
core engine for livefs modifications
"""

# need better documentation...

# pre merge triggers
# post merge triggers
# ordering?

import operator

from pkgcore.fs import contents, livefs
from pkgcore.plugin import get_plugins
from pkgcore.merge import errors
from pkgcore.interfaces import observer as observer_mod
from pkgcore.merge.const import REPLACE_MODE, INSTALL_MODE, UNINSTALL_MODE

from snakeoil.mappings import LazyValDict, ImmutableDict, StackedDict
from snakeoil import currying

from snakeoil.demandload import demandload
demandload(globals(), 'errno')

def alias_cset(alias, engine, csets):
    """alias a cset to another"""
    return csets[alias]


def map_new_cset_livefs(engine, csets, cset_name='raw_new_cset'):
    initial = csets[cset_name]
    ondisk = contents.contentsSet(livefs.intersect(initial.iterdirs(),
        realpath=True))
    livefs.recursively_fill_syms(ondisk)
    ret = initial.map_directory_structure(ondisk, add_conflicting_sym=False)
    return ret


class MergeEngine(object):

    install_hooks = dict((x, []) for x in [
            "sanity_check", "pre_merge", "merge", "post_merge", "final"])
    uninstall_hooks = dict((x, []) for x in [
            "sanity_check", "pre_unmerge", "unmerge", "post_unmerge", "final"])
    replace_hooks = dict((x, []) for x in set(
            install_hooks.keys() + uninstall_hooks.keys()))

    install_csets = {"install_existing":"get_install_livefs_intersect",
        "new_cset": map_new_cset_livefs,
        "install":currying.partial(alias_cset, 'new_cset'),
        "replace":currying.partial(alias_cset, 'new_cset')}
    uninstall_csets = {
        "uninstall_existing":currying.partial(alias_cset, "old_cset"),
        "uninstall":currying.partial(alias_cset, "old_cset"),
        "old_cset":"get_uninstall_livefs_intersect"}
    replace_csets = dict(install_csets)
    replace_csets.update(uninstall_csets)
    replace_csets["modifying"] = (
        lambda e, c: c["install"].intersection(c["uninstall"]))
    replace_csets["uninstall"] = "get_remove_cset"
    replace_csets["replace"] = "get_replace_cset"
    replace_csets["install_existing"] = "get_install_livefs_intersect"

    install_csets_preserve = ["new_cset"]
    uninstall_csets_preserve = ["old_cset"]
    replace_csets_preserve = ["new_cset", "old_cset"]


    def __init__(self, mode, hooks, csets, preserves, observer, offset=None):
        if observer is None:
            observer = observer_mod.repo_observer()
        self.observer = observer
        self.mode = mode

        self.hooks = ImmutableDict((x, []) for x in hooks)

        self.preserve_csets = []
        self.cset_sources = {}
        # instantiate these seperately so their values are preserved
        self.preserved_csets = LazyValDict(
            self.preserve_csets, self._get_cset_source)
        for k, v in csets.iteritems():
            if isinstance(v, basestring):
                v = getattr(self, v, v)
            if not callable(v):
                raise TypeError(
                    "cset values must be either the string name of "
                    "existing methods, or callables (got %s)" % v)

            if k in preserves:
                self.add_preserved_cset(k, v)
            else:
                self.add_cset(k, v)

        if offset is None:
            offset = "/"
        self.offset = offset

        # merge in default triggers first.
        for trigger in get_plugins('triggers'):
            t = trigger()
            t.register(self)

        # merge in overrides
        for hook, triggers in hooks.iteritems():
            for trigger in triggers:
                self.add_trigger(hook, trigger)

        self.regenerate_csets()
        for x in hooks.keys():
            setattr(self, x, currying.partial(self.execute_hook, x))

    @classmethod
    def install(cls, pkg, offset=None, observer=None):

        """
        generate a MergeEngine instance configured for uninstalling a pkg

        @param pkg: L{pkgcore.package.metadata.package} instance to install
        @param offset: any livefs offset to force for modifications
        @return: L{MergeEngine}

        """

        hooks = dict(
            (k, [y() for y in v])
            for (k, v) in cls.install_hooks.iteritems())

        csets = dict(cls.install_csets)
        if "raw_new_cset" not in csets:
            csets["raw_new_cset"] = currying.post_curry(cls.get_pkg_contents, pkg)
        o = cls(
            INSTALL_MODE, hooks, csets, cls.install_csets_preserve,
            observer, offset=offset)

        if o.offset != '/':
            # wrap the results of new_cset to pass through an offset generator
            o.cset_sources["new_cset"] = currying.post_curry(
                o.generate_offset_cset, o.cset_sources["new_cset"])

        o.new = pkg
        return o

    @classmethod
    def uninstall(cls, pkg, offset=None, observer=None):

        """
        generate a MergeEngine instance configured for uninstalling a pkg

        @param pkg: L{pkgcore.package.metadata.package} instance to uninstall,
            must be from a livefs vdb
        @param offset: any livefs offset to force for modifications
        @return: L{MergeEngine}
        """

        hooks = dict(
            (k, [y() for y in v])
            for (k, v) in cls.uninstall_hooks.iteritems())
        csets = dict(cls.uninstall_csets)
        if "raw_old_cset" not in csets:
            csets["raw_old_cset"] = currying.post_curry(cls.get_pkg_contents,
                pkg)
        o = cls(
            UNINSTALL_MODE, hooks, csets, cls.uninstall_csets_preserve,
            observer, offset=offset)

        if o.offset != '/':
            # wrap the results of new_cset to pass through an offset generator
            o.cset_sources["old_cset"] = currying.post_curry(
                o.generate_offset_cset, o.cset_sources["old_cset"])

        o.old = pkg
        return o

    @classmethod
    def replace(cls, old, new, offset=None, observer=None):

        """
        generate a MergeEngine instance configured for replacing a pkg.

        @param old: L{pkgcore.package.metadata.package} instance to replace,
            must be from a livefs vdb
        @param new: L{pkgcore.package.metadata.package} instance
        @param offset: any livefs offset to force for modifications
        @return: L{MergeEngine}

        """

        hooks = dict(
            (k, [y() for y in v])
            for (k, v) in cls.replace_hooks.iteritems())

        csets = dict(cls.replace_csets)

        csets.setdefault('raw_old_cset', currying.post_curry(cls.get_pkg_contents, old))
        csets.setdefault('raw_new_cset', currying.post_curry(cls.get_pkg_contents, new))

        o = cls(
            REPLACE_MODE, hooks, csets, cls.replace_csets_preserve,
            observer, offset=offset)

        if o.offset != '/':
            for k in ("old_cset", "new_cset"):
                # wrap the results of new_cset to pass through an
                # offset generator
                o.cset_sources[k] = currying.post_curry(
                    o.generate_offset_cset, o.cset_sources[k])

        o.old = old
        o.new = new
        return o

    def regenerate_csets(self):
        """
        internal function, reset non preserverd csets.

        Used in transitioning between hook points
        """
        self.csets = StackedDict(self.preserved_csets,
            LazyValDict(self.cset_sources, self._get_cset_source))

    def _get_cset_source(self, key):
        return self.cset_sources[key](self, self.csets)

    def add_preserved_cset(self, cset_name, func):
        """
        register a cset generator for use.

        The cset will stay in memory until the engine finishes all steps.

        @param cset_name: what to call the generated cset
        @param func: callable to get the cset
        """
        self.add_cset(cset_name, func)
        self.preserve_csets.append(cset_name)

    def add_cset(self, cset_name, func):
        """
        regiser a cset generator for use.

        The cset will be released from memory when it's no longer used.

        @param cset_name: what to call the generated cset
        @param func: callable to get the cset
        """
        if not callable(func):
            raise TypeError("func must be a callable")
        if not isinstance(cset_name, basestring):
            raise TypeError("cset_name must be a string")
        self.cset_sources[cset_name] = func

    def add_trigger(self, hook_name, trigger, required_csets):
        """
        register a L{pkgcore.merge.triggers.base} instance to be executed

        @param hook_name: engine step to hook the trigger into
        @param trigger: L{triggers<pkgcore.merge.triggers.base>} to add
        """
        if hook_name not in self.hooks:
            raise KeyError("trigger %r's hook %s isn't a known hook" %
                (trigger, hook_name))

        if required_csets is not None:
            for rcs in required_csets:
                if rcs not in self.cset_sources:
                    if isinstance(rcs, basestring):
                        raise errors.TriggerUnknownCset(trigger, rcs)

        self.hooks[hook_name].append(trigger)

    def execute_hook(self, hook):
        """
        execute any triggers bound to a hook point
        """
        try:
            self.phase = hook
            self.regenerate_csets()
            for trigger in sorted(self.hooks[hook],
                key=operator.attrgetter("priority")):
                # error checking needed here.
                self.observer.trigger_start(hook, trigger)
                try:
                    trigger(self, self.csets)
                finally:
                    self.observer.trigger_end(hook, trigger)
        finally:
            self.phase = None

    @staticmethod
    def generate_offset_cset(engine, csets, cset_generator):
        """generate a cset with offset applied"""
        return cset_generator(engine, csets).insert_offset(engine.offset)

    @staticmethod
    def get_pkg_contents(engine, csets, pkg):
        """generate the cset of what files shall be merged to the livefs"""
        return pkg.contents.clone()

    @staticmethod
    def get_remove_cset(engine, csets):
        """generate the cset of what files shall be removed from the livefs"""
        return csets["old_cset"].difference(csets["new_cset"])

    @staticmethod
    def get_replace_cset(engine, csets):
        """Return the cset of what will be replaced going from old->new pkg."""
        return csets["new_cset"].intersection(csets["old_cset"])

    @staticmethod
    def _get_livefs_intersect_cset(engine, csets, cset_name, realpath=True):
        """generates the livefs intersection against a cset"""
        return contents.contentsSet(livefs.intersect(csets[cset_name],
            realpath=realpath))

    @staticmethod
    def get_install_livefs_intersect(engine, csets):
        return engine._get_livefs_intersect_cset(engine, csets, "install")

    @staticmethod
    def get_uninstall_livefs_intersect(engine, csets):
        return engine._get_livefs_intersect_cset(engine, csets, "raw_old_cset")

    alias_cset = staticmethod(alias_cset)
