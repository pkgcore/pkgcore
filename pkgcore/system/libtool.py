# Copyright: 2010 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD 3 clause

from snakeoil.lists import stable_unique
from snakeoil.currying import partial, post_curry
from snakeoil.data_source import local_source
from os.path import basename, dirname
import re, operator

from pkgcore.merge import triggers

x11_sub = post_curry(partial(re.compile("X11R6/+lib").sub,
    "lib"), 1)
local_sub = post_curry(partial(re.compile("local/+lib").sub,
    "lib"), 1)
pkgconfig1_sub = post_curry(partial(
    re.compile("usr/+lib[^/]*/+pkgconfig/+\.\./\.\.").sub,
    "usr"), 1)
pkgconfig2_sub = post_curry(partial(
    re.compile("usr/+lib[^/]*/+pkgconfig/+\.\.").sub,
    "usr"), 1)
flags_match = re.compile("-(?:mt|mthreads|kthread|Kthread|pthread"
    "|pthreads|-thread-safe|threads)").match


class UnknownData(Exception):

    def __init__(self, line, token=None):
        self.token, self.line = token, line

    def __str__(self):
        s = "we don't know how to parse line %r" % (self.line,)
        if self.token:
            s += "specifically token %r" % (self.token,)
        return s

def parse_lafile(handle):
    d = {}
    for line in handle:
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        try:
            key, val = line.split("=", 1)
        except ValueError:
            raise UnknownData(line)
        # ' is specifically forced by libtdl implementation
        if len(val) >= 2 and val[0] == val[-1] and val[0] == "'":
            val = val[1:-1]
        d[key] = val
    return d


def rewrite_lafile(handle):
    data = parse_lafile(handle)
    raw_dep_libs = data.get("dependency_libs", False)
    if not raw_dep_libs:
        return False, None

    original_libs = raw_dep_libs.split()
    rpaths, libs, libladirs, inherited_flags = [], [], [], []
    original_inherited_flags = data.get("inherited_linker_flags", [])

    for item in stable_unique(original_libs):
        if item.startswith("-l"):
            libs.append(item)
        elif item.endswith(".la"):
            base = basename(item)
            if base.startswith("lib"):
                # convert to -l; punt .la, and 'lib' prefix
                libs.append("-l" + base[3:-3])
                libladirs.append("-L" + dirname(item))
            else:
                libs.append(item)
        elif item.startswith("-L"):
                # this is heinous, but is what the script did.
                item = x11_sub(item)
                item = local_sub(item)
                item = pkgconfig1_sub(item)
                item = pkgconfig2_sub(item)
                libladirs.append(item)
        elif item.startswith("-R"):
            rpaths.append(item)
        elif flags_match(item):
            if inherited_flags:
                inherited_flags.append(item)
            else:
                libs.append(item)
        else:
            raise UnknownData(raw_dep_libs, item)
    libs = stable_unique(rpaths + libladirs + libs)
    inherited_flags = stable_unique(inherited_flags)
    if libs == original_libs and inherited_flags == original_inherited_flags:
        return False, None

    # must be prefixed with a space
    data["dependency_libs"] = ' ' + (' '.join(libs))
    if inherited_flags:
        # must be prefixed with a space
        data["inherited_flags"] = ' ' + (' '.join(inherited_flags))
    return True, "\n".join("%s='%s'" % (k, v) for k,v in sorted(data.iteritems()))

def fix_fsobject(location):
    from pkgcore.fs import livefs, fs
    for obj in livefs.iter_scan(location):
        if not fs.isreg(obj) or not obj.basename.endswith(".la"):
            continue

        updated, content = rewrite_lafile(open(obj.location, 'r'))
        if updated:
            open(obj.location, 'w').write(content)


class FixLibtoolArchivesTrigger(triggers.base):

    required_csets = ('install',)
    _engine_types = triggers.INSTALLING_MODES
    _hooks = ('pre_merge',)

    def trigger(self, engine, cset):
        updates = []
        for obj in cset.iterfiles():
            if not obj.basename.endswith(".la"):
                continue
            handle = obj.data.text_fileobj()
            updated, content = rewrite_lafile(handle)
            if not updated:
                continue

            engine.observer.info("rewriting libtool archive %s" % (obj.location,))
            source = engine.get_writable_fsobj(obj, empty=True)
            source.text_fileobj(True).write(content)
            # force chksums to be regenerated
            updates.append(obj.change_attributes(data=source,
                chksums=None))
        cset.update(updates)
