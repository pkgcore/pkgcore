"""
ebuild tree manifest/digest support
"""

__all__ = ("parse_manifest", "Manifest")

import errno
import operator
import os

from snakeoil.chksum import get_handler
from snakeoil.mappings import ImmutableDict

from .. import gpg
from ..fs.livefs import iter_scan
from ..package import errors
from . import cpv


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
            yield chf, int(sum, 16)


def parse_manifest(source, ignore_gpg=True):
    types = {"DIST": {}, "AUX": {}, "EBUILD": {}, "MISC": {}}
    # manifest v2 format: (see glep 44 for exact rules)
    # TYPE filename size (CHF sum)+
    # example 'type' entry, all one line
    # MISC metadata.xml 219 RMD160 613195ece366b33606e71ff1753be048f2507841 SHA1 d162fb909241ef50b95a3539bdfcde95429bdf81 SHA256 cbd3a20e5c89a48a842f7132fe705bf39959f02c1025052efce8aad8a8baa8dc
    # manifest v1 format is
    # CHF sum filename size
    # note that we do _not_ support manifest1
    chf_types = set(["size"])
    f = None
    try:
        if isinstance(source, str):
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
                raise errors.ParseChksumError(
                    source, f"unknown manifest type: {line[0]}: {line!r}")
            if len(line) % 2 != 1:
                raise errors.ParseChksumError(
                    source,
                    "manifest 2 entry doesn't have right "
                    "number of tokens, %i: %r" %
                    (len(line), line))
            chf_types.update(line[3::2])
            # this is a trick to do pairwise collapsing;
            # [size, 1] becomes [(size, 1)]
            i = iter(line[3:])
            d[line[1]] = [("size", int(line[2]))] + list(convert_chksums(zip(i, i)))
    except (IndexError, ValueError):
        raise errors.ParseChksumError(source, 'invalid data format')
    finally:
        if f is not None and f.close:
            f.close()

    for t, d in types.items():
        types[t] = ImmutableDict((k, dict(v)) for k, v in d.items())
    # ordering annoyingly matters. bad api.
    return [types[x] for x in ("DIST", "AUX", "EBUILD", "MISC")]


class Manifest:

    def __init__(self, path, enforce_gpg=False, thin=False, allow_missing=False):
        self.path = path
        self.thin = thin
        self.allow_missing = allow_missing
        self._gpg = enforce_gpg
        self._sourced = False

    def _pull_manifest(self):
        if self._sourced:
            return
        try:
            data = parse_manifest(self.path, ignore_gpg=self._gpg)
        except EnvironmentError as e:
            if not (self.thin or self.allow_missing) or e.errno != errno.ENOENT:
                raise errors.ParseChksumError(self.path, e) from e
            data = {}, {}, {}, {}
        except errors.ChksumError as e:
            # recreate cpv from manifest path
            catpn = os.sep.join(self.path.split(os.sep)[-3:-1])
            pkg = cpv.UnversionedCPV(catpn)
            raise errors.MetadataException(pkg, 'manifest', str(e))
        self._dist, self._aux, self._ebuild, self._misc = data
        self._sourced = True

    def update(self, fetchables, chfs=None):
        """Update the related Manifest file.

        :param fetchables: fetchables of the package
        """

        if self.thin and not fetchables:
            # Manifest files aren't necessary with thin manifests and no distfiles
            return

        _key_sort = operator.itemgetter(0)

        excludes = frozenset(["CVS", ".svn", "Manifest"])
        aux, ebuild, misc = {}, {}, {}
        if not self.thin:
            filesdir = '/files/'
            for obj in iter_scan('/', offset=os.path.dirname(self.path), chksum_types=chfs):
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
                    raise Exception("Unexpected directory found in %r; %r" % (self.path, obj.dirname))
                d[pathname] = dict(obj.chksums)

        handle = open(self.path, 'w')

        # write it in alphabetical order; aux gets flushed now.
        for path, chksums in sorted(aux.items(), key=_key_sort):
            _write_manifest(handle, 'AUX', path, chksums)

        # next dist...
        for fetchable in sorted(fetchables, key=operator.attrgetter('filename')):
            _write_manifest(
                handle, 'DIST', os.path.basename(fetchable.filename),
                dict(fetchable.chksums))

        # then ebuild and misc
        for mtype, inst in (("EBUILD", ebuild), ("MISC", misc)):
            for path, chksum in sorted(inst.items(), key=_key_sort):
                _write_manifest(handle, mtype, path, chksum)

    @property
    def aux_files(self):
        self._pull_manifest()
        return self._aux

    @property
    def distfiles(self):
        self._pull_manifest()
        return self._dist

    @property
    def ebuilds(self):
        self._pull_manifest()
        return self._ebuild

    @property
    def misc(self):
        self._pull_manifest()
        return self._misc
