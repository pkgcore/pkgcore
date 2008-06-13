from tempfile import TemporaryFile
from pkgcore.test import TestCase as OrigTestCase
from pkgcore.ebuild import eix_utils

def split_bytes(n):
    if not n:
        l = [0]
    else:
        l = []
        while n:
            l.append(n & 0xFF)
            n = n >> 8
    return reversed(l)

def make_number(n):
    res = [chr(x) for x in split_bytes(n)]
    l = len(res)-1
    if res[0] == '\xFF':
        res[0] = '\x00'
        res.insert(0, "\xFF")
        l -= 1
    return ''.join(['\xFF'*l]+res)

class TestCase(OrigTestCase):
    # We use this because the CPy is picky about what it accepts
    def file(self, s=None):
        f = TemporaryFile()
        if s is not None:
            f.write(s)
            f.seek(0)
        return f


class TestNativeNumber(TestCase):
    test = (
        (0x00, "\x00"),
        (0xFE, "\xFE"),
        (0xFF, "\xFF\x00"),
        (0x0100, "\xFF\x01\x00"),
        (0x01FF, "\xFF\x01\xFF"),
        (0xFEFF, "\xFF\xFE\xFF"),
        (0xFF00, "\xFF\xFF\x00\x00"),
        (0xFF01, "\xFF\xFF\x00\x01"),
        (0x010000, "\xFF\xFF\x01\x00\x00"),
        (0xABCDEF, "\xFF\xFF\xAB\xCD\xEF"),
        (0xFFABCD, "\xFF\xFF\xFF\x00\xAB\xCD"),
        (0x01ABCDEF, "\xFF\xFF\xFF\x01\xAB\xCD\xEF"),
    )

    f = staticmethod(eix_utils.native_number)
    fil = open("temp", "w+")

    def test_conv(self):
        for res, s in self.test:
            self.assertEqual(self.f(self.file(s)), res)
        self.assertEqual(0xFF, self.f(self.file("\xFF\x00\x08")))

    def test_trailing(self):
        self.assertRaises(ValueError, self.f, self.file("\xFF"))
        self.assertEqual(self.f(self.file("\xFF\x01\x08\x08\x08")), 0x0108)

    def test_short(self):
        self.assertRaises(ValueError, self.f, self.file("\xFF\xFF\xFF"))

    def test_make_number(self):
        for x in xrange(1000):
            self.assertEqual(x, self.f(self.file(make_number(x))))

class TestCPyNumber(TestNativeNumber):
    f = staticmethod(eix_utils.number)
    if eix_utils.number == eix_utils.native_number:
        skip = "CPy extension not available"

class TestString(TestCase):
    f = staticmethod(eix_utils.string)
    # More tests? What else should be tested?
    test = ("asdf", "asdfasdf", "1234567890")
    def testit(self):
        f = self.file()
        for x in self.test:
            f.seek(0)
            f.write(make_number(len(x)))
            f.write(x)
            f.seek(0)
            s = self.f(f)
            self.assertEqual(s, x)


class TestVector(TestCase):
    f = staticmethod(eix_utils.vector)
    def testit(self):
        stuff = "abcdefghijk"
        i = [0] # stupid local var hack
        f = self.file()
        def vf(f):
            i[0] += 1
            return f.read(1)
        f.write(make_number(len(stuff)))
        f.write(stuff)
        f.seek(0)
        t = self.f(f, vf)
        self.assertEqual(i[0], len(stuff))
        self.assertEqual(''.join(t), stuff)

def make_version_part(type, s):
    return make_number(len(s) << 5|type)+s

class TestVersionPart(TestCase):
    f = staticmethod(eix_utils.version_part)
    test = ((10, "1"), (9, "2"), (8, "c"), (3, "12"), (1, ""),
        (5, "01"), (6, "01"), (0, "-foo"))
    def testit(self):
        f = self.file()
        for x in self.test:
            f.write(make_version_part(*x))
        f.seek(0)
        l = [self.f(f) for x in xrange(len(self.test))]
        self.assertEqual("1.2c_pre12_alpha-r01.01-foo", ''.join(l))
