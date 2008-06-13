def _count_leading(f):
    n = 0
    while True:
        c = f.read(1)
        if not c:
            raise ValueError
        elif c == '\xFF':
            n += 1
        else:
            f.seek(-1, 1) # Backtrack
            break
    return n

def native_number(f):
    num = 0
    n = _count_leading(f)
    c = f.read(1)
    if not c:
        raise ValueError
    if n and c == '\x00':
        num = 0xFF
        n -= 2
    else:
        f.seek(-1, 1) # Backtrack
    n += 1
    s = f.read(n)
    if n and not s:
        raise ValueError
    for c in s:
        num = num << 8
        num += ord(c)
    return num

try:
    from pkgcore.ebuild._eix import number
except ImportError:
    number = native_number

def string(f):
    length = number(f)
    return f.read(length)

def vector(file, func):
    amount = number(file)
    return tuple(func(file) for x in xrange(amount))

def hash(f):
    return vector(f, string)

def hashed_words(f):
    return vector(f, number)

def hash_attr(name):
    def f(self):
        return getattr(self._repo, name+"s")[getattr(self, "_"+name)]
    return f


def hashed_word_attr(name):
    def f(self):
        p = getattr(self._repo, name)
        s = ' '.join(p[x] for x in getattr(self, "_"+name))
        setattr(self, name, s)
        return s
    return f

_parts = {
    0: "",
    1: "_alpha",
    2: "_beta",
    3: "_pre",
    4: "_rc",
    5: "-r",
    6: ".",
    7: "_p",
    8: "",
    9: ".",
    10: ""
}
def version_part(f):
    n = number(f)
    part = n & 0xF
    length = n >> 5
    st = f.read(length)
    return _parts[part]+st


def bitset(c):
    d = {}
    if c & 0x01:
        d["package.mask"] = True
    if c & 0x02:
        d["profile"] = True
    if c & 0x04:
        d["system"] = True
    if c & 0x10:
        d["fetch"] = True
    if c & 0x20:
        d["mirror"] = True
    return d
