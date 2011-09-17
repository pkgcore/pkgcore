# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
core engine for livefs modifications
"""

__all__ = ("alias_cset", "map_new_cset_livefs", "MergeEngine")

# need better documentation...

# pre merge triggers
# post merge triggers
# ordering?

import operator

from pkgcore.fs import contents, livefs
from pkgcore.plugin import get_plugins
from pkgcore.merge import errors
from pkgcore.operations import observer as observer_mod
from pkgcore.merge.const import REPLACE_MODE, INSTALL_MODE, UNINSTALL_MODE

from snakeoil import compatibility
from snakeoil.mappings import LazyValDict, ImmutableDict, StackedDict
from snakeoil import currying, data_source
from snakeoil.osutils import normpath

from snakeoil.demandload import demandload
demandload(globals(),
    "tempfile",
    "traceback",
    "snakeoil:stringio",
)

def alias_cset(alias, engine, csets):
    """alias a cset to another"""
    return csets[alias]


def map_new_cset_livefs(engine, csets, cset_name='new_cset'):
    """find the syms on disk that redirect new_cset, and return a cset
    localized to the livefs"""
    initial = csets[cset_name]
    ondisk = contents.contentsSet(livefs.intersect(initial.iterdirs(),
        realpath=True))
    livefs.recursively_fill_syms(ondisk)
    ret = initial.map_directory_structure(ondisk, add_conflicting_sym=True)
    return ret


class MergeEngine(object):

    install_hooks = dict((x, []) for x in [
            "sanity_check", "pre_merge", "merge", "post_merge", "final"])
    uninstall_hooks = dict((x, []) for x in [
            "sanity_check", "pre_unmerge", "unmerge", "post_unmerge", "final"])
    replace_hooks = dict((x, []) for x in set(
            install_hooks.keys() + uninstall_hooks.keys()))

    install_csets = {"install_existing":"get_install_livefs_intersect",
        "resolved_install": map_new_cset_livefs,
        'new_cset':currying.partial(alias_cset, 'raw_new_cset'),
        "install":currying.partial(alias_cset, 'new_cset'),
        "replace":currying.partial(alias_cset, 'new_cset')}
    uninstall_csets = {
        "uninstall_existing":currying.partial(alias_cset, "uninstall"),
        "uninstall":currying.partial(alias_cset, "old_cset"),
        "old_cset":"get_uninstall_livefs_intersect"}
    replace_csets = dict(install_csets)
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
        offset=None, disable_plugins=False):
        if observer is None:
            observer = observer_mod.repo_observer(observer_mod.null_output)
        self.observer = observer
        self.mode = mode
        if tempdir is not None:
            tempdir = normpath(tempdir) + '/'
        self.tempdir = tempdir

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

        if not disable_plugins:
            # merge in default triggers first.
            for trigger in get_plugins('triggers'):
                t = trigger()
                t.register(self)

        # merge in overrides
        for hook, triggers in hooks.iteritems():
            for trigger in triggers:
                self.add_trigger(hook, trigger)

        self.regenerate_csets()
        for x in hooks:
            setattr(self, x, currying.partial(self.execute_hook, x))

    @classmethod
    def install(cls, tempdir, pkg, offset=None, observer=None,
        disable_plugins=False):

        """
        generate a MergeEngine instance configured for uninstalling a pkg

        :param tempdir: tempspace for the merger to use; this space it must
            control alone, no sharing.
        :param pkg: :obj:`pkgcore.package.metadata.package` instance to install
        :param offset: any livefs offset to force for modifications
        :param disable_plugins: if enabled, run just the triggers passed in
        :return: :obj:`MergeEngine`

        """

        hooks = dict(
            (k, [y() for y in v])
            for (k, v) in cls.install_hooks.iteritems())

        csets = dict(cls.install_csets)
        if "raw_new_cset" not in csets:
            csets["raw_new_cset"] = currying.post_curry(cls.get_pkg_contents, pkg)
        o = cls(
            INSTALL_MODE, tempdir, hooks, csets, cls.install_csets_preserve,
            observer, offset=offset, disable_plugins=disable_plugins)

        if o.offset != '/':
            # wrap the results of new_cset to pass through an offset generator
            o.cset_sources["raw_new_cset"] = currying.post_curry(
                o.generate_offset_cset, o.cset_sources["raw_new_cset"])

        o.new = pkg
        return o

    @classmethod
    def uninstall(cls, tempdir, pkg, offset=None, observer=None,
        disable_plugins=False):

        """
        generate a MergeEngine instance configured for uninstalling a pkg

        :param tempdir: tempspace for the merger to use; this space it must
            control alone, no sharing.
        :param pkg: :obj:`pkgcore.package.metadata.package` instance to uninstall,
            must be from a livefs vdb
        :param offset: any livefs offset to force for modifications
        :param disable_plugins: if enabled, run just the triggers passed in
        :return: :obj:`MergeEngine`
        """

        hooks = dict(
            (k, [y() for y in v])
            for (k, v) in cls.uninstall_hooks.iteritems())
        csets = dict(cls.uninstall_csets)
        if "raw_old_cset" not in csets:
            csets["raw_old_cset"] = currying.post_curry(cls.get_pkg_contents,
                pkg)
        o = cls(
            UNINSTALL_MODE, tempdir, hooks, csets, cls.uninstall_csets_preserve,
            observer, offset=offset, disable_plugins=disable_plugins)

        if o.offset != '/':
            # wrap the results of new_cset to pass through an offset generator
            o.cset_sources["old_cset"] = currying.post_curry(
                o.generate_offset_cset, o.cset_sources["old_cset"])

        o.old = pkg
        return o

    @classmethod
    def replace(cls, tempdir, old, new, offset=None, observer=None,
        disable_plugins=False):

        """
        generate a MergeEngine instance configured for replacing a pkg.

        :param tempdir: tempspace for the merger to use; this space it must
            control alone, no sharing.
        :param old: :obj:`pkgcore.package.metadata.package` instance to replace,
            must be from a livefs vdb
        :param new: :obj:`pkgcore.package.metadata.package` instance
        :param offset: any livefs offset to force for modifications
        :param disable_plugins: if enabled, run just the triggers passed in
        :return: :obj:`MergeEngine`

        """

        hooks = dict(
            (k, [y() for y in v])
            for (k, v) in cls.replace_hooks.iteritems())

        csets = dict(cls.replace_csets)

        csets.setdefault('raw_old_cset', currying.post_curry(cls.get_pkg_contents, old))
        csets.setdefault('raw_new_cset', currying.post_curry(cls.get_pkg_contents, new))

        o = cls(
            REPLACE_MODE, tempdir, hooks, csets, cls.replace_csets_preserve,
            observer, offset=offset, disable_plugins=disable_plugins)

        if o.offset != '/':
            for k in ("raw_old_cset", "raw_new_cset"):
                # wrap the results of new_cset to pass through an
                # offset generator
                o.cset_sources[k] = currying.post_curry(
                    o.generate_offset_cset, o.cset_sources[k])

        o.old = old
        o.new = new
        return o

    def replace_cset(self, name, new_cset):
        """
        replace the cset referenced by this engine; use only if you know what you're doing

        :param name: name of the cset
        :new_cset: a contentsSet instance to use
        """
        if name in self.preserved_csets:
            # yes this is evil awareness of LazyValDict internals...
            self.preserved_csets._vals[name] = new_cset
        else:
            raise KeyError("attempted to replace a non preserved cset: %s" % (name,))

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

        :param cset_name: what to call the generated cset
        :param func: callable to get the cset
        """
        self.add_cset(cset_name, func)
        self.preserve_csets.append(cset_name)

    def add_cset(self, cset_name, func):
        """
        regiser a cset generator for use.

        The cset will be released from memory when it's no longer used.

        :param cset_name: what to call the generated cset
        :param func: callable to get the cset
        """
        if not callable(func):
            raise TypeError("func must be a callable")
        if not isinstance(cset_name, basestring):
            raise TypeError("cset_name must be a string")
        self.cset_sources[cset_name] = func

    def add_trigger(self, hook_name, trigger, required_csets):
        """
        register a :obj:`pkgcore.merge.triggers.base` instance to be executed

        :param hook_name: engine step to hook the trigger into
        :param trigger: :class:`pkgcore.merge.triggers.base` to add
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
                    try:
                        trigger(self, self.csets)
                    except compatibility.IGNORED_EXCEPTIONS:
                        raise
                    except errors.BlockModification, e:
                        self.observer.error("modification was blocked by "
                            "trigger %r: %s" % (trigger, e))
                        raise
                    except errors.ModificationError, e:
                        self.observer.error("modification error occured "
                            "during trigger %r: %s" % (trigger,e))
                        raise
                    except Exception, e:
                        if not trigger.suppress_exceptions:
                            raise

                        handle = stringio.text_writable()
                        traceback.print_exc(file=handle)

                        self.observer.warn("unhandled exception caught and "
                            "suppressed:\n%s" % (handle.getvalue(),))
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
        return csets["old_cset"].difference(csets["resolved_install"])

    @staticmethod
    def get_replace_cset(engine, csets):
        """Return the cset of what will be replaced going from old->new pkg."""
        return csets["resolved_install"].intersection(csets["old_cset"])

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

    def get_merged_cset(self, strip_offset=True):
        cset = self.csets["install"]
        if self.offset not in (None, '/') and strip_offset:
            rewrite = contents.change_offset_rewriter(self.offset, '/',
                cset)
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
                obj = data_source.local_source(path, True,
                    encoding=source.encoding)

                if empty:
                    obj.bytes_fileobj(True).truncate(0)
                return obj

        # clone it into tempspace; it's required we control the tempspace,
        # so this function is safe in our usage.
        path = tempfile.mktemp(prefix='merge-engine-', dir=self.tempdir)

        # XXX: annoying quirk of python, we don't want append mode, so 'a+'
        # isn't viable; wr will truncate the file, so data_source uses r+.
        # this however doesn't allow us to state "create if missing"
        # so we create it ourselves.  Annoying, but so it goes.
        # just touch the filepath.
        open(path, 'w')
        new_source = data_source.local_source(path, True,
            encoding=getattr(fsobj, 'encoding', None))

        if source and not empty:
            data_source.transfer(source.bytes_fsobj(), new_source.bytes_fsobj(True))
        return new_source
