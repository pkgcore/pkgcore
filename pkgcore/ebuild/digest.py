# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
ebuild tree manifest/digest support
"""
from itertools import izip
from pkgcore.chksum import errors, gpg
from pkgcore.util.obj import make_SlottedDict_kls

def parse_digest(path, throw_errors=True):
    d = {}
    chf_keys = set(["size"])
    try:
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
                    d[l[2]] = {chf:long(l[1], 16), "size":long(l[3])}
                else:
                    d2[chf] = long(l[1], 16)
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


    
def parse_manifest(path, throw_errors=True):
    d = {}
    dist, aux, ebuild, misc = {}, {}, {}, {}
    types = (("DIST", dist), ("AUX", aux), ("EBUILD", ebuild), ("MISC", misc))
    files = {}
    # type format (see glep 44 for exact rules)
    # TYPE filename size (CHF sum)+
    # example 'type' entry, all one line
    #MISC metadata.xml 219 RMD160 613195ece366b33606e71ff1753be048f2507841 SHA1 d162fb909241ef50b95a3539bdfcde95429bdf81 SHA256 cbd3a20e5c89a48a842f7132fe705bf39959f02c1025052efce8aad8a8baa8dc
    # old style manifest
    # CHF sum filename size
    chf_types = set(["size"])
    try:
        f = None
        try:
            f = open(path, "r", 32384)
            for data in gpg.skip_signatures(f):
                l = data.split()
                for t, d in types:
                    if l[0] != t:
                        continue
                    if len(l) % 2 != 1:
                        if throw_errors:
                            raise errors.ParseChksumError(path,
                                "manifest 2 entry doesn't have right "
                                "number of tokens, %i: %r" % 
                                (len(line), line))
                    else:
                        chf_types.update(l[3::2])
                        # this is a trick to do pairwise collapsing;
                        # [size, 1] becomes [(size, 1)]
                        i = iter(l[3:])
                        d[l[1]] = [("size", long(l[2]))] + \
                            [(chf.lower(), long(sum, 16))
                                for chf, sum in izip(i, i)]
                    break
                else:
                    if len(l) != 4:
                        if throw_errors:
                            raise errors.ParseChksumError(path,
                                "line count was not 4, was %i: %r" %
                                (len(l, line)))
                        continue
                    chf_types.add(l[0])
                    files.setdefault(l[2], []).append(
                        [long(l[3]), l[0].lower(), long(l[1], 16)])
            
        except (OSError, IOError, TypeError), e:
            raise errors.ParseChksumError("failed parsing %r" % path, e)
    finally:
        if f is not None or not f.close:
            f.close()

    # collapse files into 4 types, convert to lower mem dicts
    # doesn't handle files sublists correctly yet
    for fname, data in files.iteritems():
        for t, d in types:
            existing = d.get(fname, None)
            if existing is None:
                continue
            break
        else:
            # work around portage_manifest sucking and not
            # specifying all files in the manifest.
            if fname.endswith(".ebuild"):
                existing = ebuild.setdefault(fname, [])
            else:
                existing = misc.setdefault(fname, [])

        for chksum in data:
            if existing:
                if existing[0][1] != chksum[0]:
                    if throw_errors:
                        raise errors.ParseChksumError(path,
                            "size collision for file %s" % fname)
                else:
                    existing.append(chksum[1:])
            else:
                existing.append(("size", chksum[0]))
                existing.append(chksum[1:])

    del files

    # finally convert it to slotted dict for memory savings.
    kls = make_SlottedDict_kls(x.lower() for x in chf_types)        
    ret = []
    for t, d in types:
        for k, v in d.items():
            d[k] = kls(v)
        ret.append(d)
    return ret
