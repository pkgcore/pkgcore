# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

from pkgcore.ebuild import repo_objs
from pkgcore.interfaces.data_source import data_source

from pkgcore.test import TestCase


class TestMetadataXml(TestCase):

    @staticmethod
    def get_metadata_xml(herds=(), maintainers=(), longdescription=None):
        hs, ms, ls = "", "", ""
        if herds:
            hs = "<herd>%s</herd>\n" % "</herd><herd>".join(herds)
        if maintainers:
            ms = []
            for x in maintainers:
                ms.append("<email>%s</email>" % x[0])
                if len(x) > 1:
                    ms[-1] = "%s\n<name>%s</name>" % (ms[-1], x[1])
            ms = "<maintainer>%s</maintainer>\n" % \
                "</maintainer><maintainer>".join(ms)
        if longdescription:
            ls = "<longdescription>%s</longdescription>\n" % longdescription
        s = \
"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE pkgmetadata SYSTEM "http://www.gentoo.org/dtd/metadata.dtd">
<pkgmetadata>
%s%s%s</pkgmetadata>""" % (hs, ms, ls)
        return repo_objs.MetadataXml(data_source(s.encode('utf-8')))

    def test_maintainers(self):
        # test empty.
        self.assertEqual((), self.get_metadata_xml().maintainers)

        # test non empty, multiple
        names = ("foo@gmail.com", "monkeybone@gmail.com")
        mx = self.get_metadata_xml(maintainers=tuple(
            (x,) for x in names))
        self.assertEqual(sorted(names), sorted(str(m) for m in mx.maintainers))
        # test email/name integration.
        mx = self.get_metadata_xml(
            maintainers=(("funkymonkey@gmail.com",
                          u"funky monkey \N{SNOWMAN}"),))
        self.assertEqual((u"funky monkey \N{SNOWMAN} <funkymonkey@gmail.com>",),
                         tuple(unicode(m) for m in mx.maintainers))
        self.assertEqual("funkymonkey@gmail.com", mx.maintainers[0].email)
        self.assertEqual(u"funky monkey \N{SNOWMAN}", mx.maintainers[0].name)

    def test_herds(self):
        # empty...
        self.assertEqual((), self.get_metadata_xml().herds)

        herds = ("video", "sound")
        self.assertEqual(sorted(herds),
            sorted(self.get_metadata_xml(herds).herds))

    def test_longdesc(self):
        # empty...
        self.assertEqual(None, self.get_metadata_xml().longdescription)
        s = \
"""
I saw the best minds of my generation destroyed by madness, starving
hysterical naked, dragging themselves throughout the negro streets at dawn
looking for an angry fix, angle-headed hipsters burning for the ancient
heavenly connection to the starry dynamo in the machinery of night, who
poverty and tatters and hollowed-eyed and high sat up smoking in the
supernatural darkness of cold-water flats floating across the tops of cities
contemplating jazz, who bared their brains to Heaven under the El and saw
Mohammedan angels staggering on tenement roofs illuminated, who passed
through universities with radiant cool eyes hallucinating Arkansas and
Blake-light tragedy among the scholars of war.
"""

        self.assertEqual(" ".join(s.split()),
            self.get_metadata_xml(longdescription=s).longdescription)
