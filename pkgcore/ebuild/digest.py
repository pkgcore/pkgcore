# Copyright: 2005-2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
ebuild tree manifest/digest support
"""

__all__ = ("serialize_manifest", "parse_manifest", "Manifest")

from itertools import izip
from os.path import basename, dirname, sep

from snakeoil.chksum import get_handler
from pkgcore import gpg
from pkgcore.package import errors
from pkgcore.fs.livefs import iter_scan
from pkgcore.fs.fs import fsFile

from snakeoil.obj import make_SlottedDict_kls
from snakeoil.compatibility import any, raise_from
from snakeoil.demandload import demandload
demandload(globals(),
    "pkgcore:fetch",
    "snakeoil.lists:iflatten_instance",
    'snakeoil:mappings',
    "errno",
)

def serialize_manifest(pkgdir, fetchables):
    """
    Write a manifest given a pkg_instance

    :param pkgdir: the location of the package dir
    :param fetchables: the fetchables of the package
    """
    handle = open(pkgdir + '/Manifest', 'w')
    excludes = frozenset(["CVS", ".svn", "Manifest"])
    for file in iter_scan(pkgdir):
        if not file.is_reg:
            continue
        if excludes.intersection(file.location.split(sep)):
            continue
        type = 'misc'
        if 'files' in dirname(file.location):
            type = 'aux'
        elif basename(file.location)[-7:] ==  '.ebuild':
            type = 'ebuild'
        _write_manifest(handle, type, basename(file.location), dict(file.chksums))
    type = 'dist'
    for fetchable in iflatten_instance(fetchables, fetch.fetchable):
        _write_manifest(handle, type, basename(fetchable.filename), dict(fetchable.chksums))

def _write_manifest(handle, type, filename, chksums):
    """Convenient, internal method for writing manifests"""
    size = chksums.pop("size")
    handle.write("%s %s %i" % (type.upper(), filename, size))
    for chf, sum in chksums.iteritems():
        handle.write(" %s %s" % (chf.upper(), get_handler(chf).long2str(sum)))
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
            raise_from(errors.ParseChksumError(source, e,
                missing=(e.errno == errno.ENOENT)))
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
