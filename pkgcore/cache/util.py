# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
cache backend utilities
"""

from pkgcore.cache import errors

def mirror_cache(valid_nodes_iterable, src_cache, trg_cache, eclass_cache=None,
                 verbose_instance=None):
    """
    make a cache backend a mirror of another

    @param valid_nodes_iterable: valid keys
    @param src_cache: L{pkgcore.cache.template.database} instance
        to copy keys from
    @param trg_cache: L{pkgcore.cache.template.database} instance
        to write keys to
    @param eclass_cache: if doing eclass_cache translation,
        a L{pkgcore.ebuild.eclass_cache.cache} instance to use, else None
    @param verbose_instance: either None (defaulting to L{quiet_mirroring}),
        or a L{quiet_mirroring} derivative
    """

    if not src_cache.complete_eclass_entries and not eclass_cache:
        raise Exception(
            "eclass_cache required for cache's of class %s!" %
            src_cache.__class__)

    if verbose_instance is None:
        noise = quiet_mirroring()
    else:
        noise = verbose_instance

    dead_nodes = set(trg_cache.iterkeys())
    count = 0

    if not trg_cache.autocommits:
        trg_cache.sync(100)

    for x in valid_nodes_iterable:
        count += 1
        if x in dead_nodes:
            dead_nodes.remove(x)
        try:
            entry = src_cache[x]
        except KeyError:
            noise.missing_entry(x)
            continue
        if entry.get("INHERITED",""):
            if src_cache.complete_eclass_entries:
                if not "_eclasses_" in entry:
                    noise.corruption(x,"missing _eclasses_ field")
                    continue
                if not eclass_cache.is_eclass_data_valid(entry["_eclasses_"]):
                    noise.eclass_stale(x)
                    continue
            else:
                entry["_eclasses_"] = eclass_cache.get_eclass_data(
                    entry["INHERITED"].split(), from_master_only=True)
                if not entry["_eclasses_"]:
                    noise.eclass_stale(x)
                    continue

        # by this time, if it reaches here, the eclass has been
        # validated, and the entry has been updated/translated (if
        # needs be, for metadata/cache mainly)
        try:
            trg_cache[x] = entry
        except errors.CacheError, ce:
            noise.exception(x, ce)
            del ce
            continue

        if count >= noise.call_update_min:
            noise.update(x)
            count = 0

    if not trg_cache.autocommits:
        trg_cache.commit()

    # ok. by this time, the trg_cache is up to date, and we have a
    # dict with a crapload of cpv's. we now walk the target db,
    # removing stuff if it's in the list.
    for key in dead_nodes:
        try:
            del trg_cache[key]
        except errors.CacheError, ce:
            noise.exception(ce)
            del ce


# "More than one statement on a single line"
# pylint: disable-msg=C0321

class quiet_mirroring(object):
    """Quiet mirror_cache callback object for getting progress information."""
    # call_update_every is used by mirror_cache to determine how often
    # to call in. quiet defaults to 2^24 -1. Don't call update, 'cept
    # once every 16 million or so :)
    call_update_min = 0xffffff
    def update(self, key, *arg): pass
    def exception(self, key, *arg): pass
    def eclass_stale(self, *arg): pass
    def missing_entry(self, key): pass
    def misc(self, key, *arg): pass
    def corruption(self, key, s): pass

class non_quiet_mirroring(quiet_mirroring):
    """prints to stdout each step in cache mirroring"""

    call_update_min = 1
    def update(self, key, *arg): print "processed", key
    def exception(self, key, *arg): print "exec", key, arg
    def missing(self, key): print "key %s is missing", key
    def corruption(self, key, *arg): print "corrupt %s:" % key, arg
    def eclass_stale(self, key, *arg): print "stale %s:" % key, arg
