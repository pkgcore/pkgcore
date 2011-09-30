# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
ebuild tree manifest/digest support
"""

__all__ = ("serialize_manifest", "parse_manifest", "Manifest")

from itertools import izip
import operator
from os.path import basename, dirname

from snakeoil.chksum import get_handler
from pkgcore import gpg
from pkgcore.package import errors
from pkgcore.fs.livefs import iter_scan
from pkgcore.fs.fs import fsFile

from snakeoil.mappings import make_SlottedDict_kls
from snakeoil.compatibility import any, raise_from
from snakeoil.demandload import demandload
demandload(globals(),
    "snakeoil.lists:iflatten_instance",
    'snakeoil:mappings',
    "errno",
)


def serialize_manifest(pkgdir, fetchables, chfs=None):
    """
    Write a manifest given a pkg_instance

    :param pkgdir: the location of the package dir
    :param fetchables: the fetchables of the package
    """

    _key_sort = operator.itemgetter(0)

    handle = open(pkgdir + '/Manifest', 'w')
    excludes = frozenset(["CVS", ".svn", "Manifest"])
    aux, ebuild, misc = {}, {}, {}
    filesdir = '/files/'
    for obj in iter_scan('/', offset=pkgdir, chksum_types=chfs):
        if not obj.is_reg:
            continue
        pathname = obj.location
        if excludes.intersection(pathname.split('/')):
            continue
        if pathname.startswith(filesdir):
            d = aux
            pathname = pathname[len(filesdir):]
        elif obj.dirname == '/':
            pathname = pathname[1:]
            if obj.location[-7:] == '.ebuild':
                d = ebuild
            else:
                d = misc
        else:
            raise Exception("Unexpected directory found in %r; %r"
                % (pkgdir, obj.dirname))
        d[pathname] = dict(obj.chksums)

    # write it in alphabetical order; aux gets flushed now.
    for path, chksums in sorted(aux.iteritems(), key=_key_sort):
        _write_manifest(handle, 'AUX', path, chksums)

    # next dist...
    for fetchable in sorted(fetchables, key=operator.attrgetter('filename')):
        _write_manifest(handle, 'DIST', basename(fetchable.filename),
            dict(fetchable.chksums))

    # then ebuild and misc
    for mtype, inst in (("EBUILD", ebuild), ("MISC", misc)):
        for path, chksum in sorted(inst.iteritems(), key=_key_sort):
            _write_manifest(handle, mtype, path, chksum)


def _write_manifest(handle, chf, filename, chksums):
    """Convenient, internal method for writing manifests"""
    size = chksums.pop("size")
    handle.write("%s %s %i" % (chf.upper(), filename, size))
    for chf in sorted(chksums):
        handle.write(" %s %s" % (chf.upper(), get_handler(chf).long2str(chksums[chf])))
    handle.write('\n')


def convert_chksums(iterable):
    for chf, sum in iterable:
        chf = chf.lower()
        if chf == 'size':
            # explicit size entries are stupid, format has implicit size
            continue
        else:
            yield chf, long(sum, 16)


def parse_manifest(source, ignore_gpg=True):
    types = {"DIST":{}, "AUX":{}, "EBUILD":{}, "MISC":{}}
    # manifest v2 format: (see glep 44 for exact rules)
    # TYPE filename size (CHF sum)+
    # example 'type' entry, all one line
    #MISC metadata.xml 219 RMD160 613195ece366b33606e71ff1753be048f2507841 SHA1 d162fb909241ef50b95a3539bdfcde95429bdf81 SHA256 cbd3a20e5c89a48a842f7132fe705bf39959f02c1025052efce8aad8a8baa8dc
    # manifest v1 format is
    # CHF sum filename size
    # note that we do _not_ support manifest1
    chf_types = set(["size"])
    try:
        f = None
        try:
            if isinstance(source, basestring):
                i = f = open(source, "r", 32768)
            else:
                i = f = source.text_fileobj()
            if ignore_gpg:
                i = gpg.skip_signatures(f)
            for data in i:
                line = data.split()
                if not line:
                    continue
                d = types.get(line[0])
                if d is None:
                    raise errors.ParseChksumError(source,
                        "unknown manifest type: %s: %r" % (line[0], line))
                if len(line) % 2 != 1:
                    raise errors.ParseChksumError(source,
                        "manifest 2 entry doesn't have right "
                        "number of tokens, %i: %r" %
                        (len(line), line))
                chf_types.update(line[3::2])
                # this is a trick to do pairwise collapsing;
                # [size, 1] becomes [(size, 1)]
                i = iter(line[3:])
                d[line[1]] = [("size", long(line[2]))] + \
                    list(convert_chksums(izip(i, i)))

        except EnvironmentError, e:
            missing = (e.errno == errno.ENOENT)
            raise_from(errors.ParseChksumError(source, e,
                missing=missing))
    finally:
        if f is not None and f.close:
            f.close()

    # finally convert it to slotted dict for memory savings.
    slotted_kls = make_SlottedDict_kls(x.lower() for x in chf_types)
    for t, d in types.iteritems():
        types[t] = mappings.ImmutableDict((k, slotted_kls(v)) for k, v in d.iteritems())
    # ordering annoyingly matters. bad api.
    return [types[x] for x in ("DIST", "AUX", "EBUILD", "MISC")]


class Manifest(object):


    # left for compatibility until 0.8 (pcheck needs it)
    version = 2

    def __init__(self, source, enforce_gpg=False):
        self._source = (source, not enforce_gpg)

    def _pull_manifest(self):
        if self._source is None:
            return
        source, gpg = self._source
        data = parse_manifest(source, ignore_gpg=gpg)
        self._dist, self._aux, self._ebuild, self._misc = data
        self._source = None

    @property
    def required_files(self):
        self._pull_manifest()
        return mappings.StackedDict(self._ebuild, self._misc)

    @property
    def aux_files(self):
        self._pull_manifest()
        return self._aux

    @property
    def distfiles(self):
        self._pull_manifest()
        return self._dist
