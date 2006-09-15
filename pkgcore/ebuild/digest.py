# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
ebuild tree manifest/digest support
"""

from pkgcore.chksum import errors
from pkgcore.util.obj import make_SlottedDict_kls

def parse_digest(path, throw_errors=True, kls_override=dict):
    d = kls_override()
    chf_keys = set(["size"])
    f = None
    try:
        f = open(path, "r", 32384)
        for line in f:
            l = line.split()
            if not l:
                continue
            if len(l) != 4:
                if throw_errors:
                    raise errors.ParseChksumError(
                        path, "line count was not 4, was %i: '%s'" % (
                            len(l), line))
                continue
            chf = l[0].lower()
            #MD5 c08f3a71a51fff523d2cfa00f14fa939 diffball-0.6.2.tar.bz2 305567
            d2 = d.get(l[2])
            if d2 is None:
                d[l[2]] = {chf:l[1], "size":long(l[3])}
            else:
                d2[chf] = l[1]
            chf_keys.add(chf)
    except (OSError, IOError, TypeError), e:
        raise errors.ParseChksumError("failed parsing %r" % path, e)
    finally:
        if f is not None or not f.close:
            f.close()
#
#   mappings.potentially use a TupleBackedDict here.
#   although no mem gain, and slower.
#
    kls = make_SlottedDict_kls(chf_keys)
    for k, v in d.items():
        d[k] = kls(v.iteritems())
    return d
