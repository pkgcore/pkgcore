# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import re

from snakeoil.data_source import data_source

from pkgcore.ebuild import repo_objs
from pkgcore.test import TestCase


class TestMetadataXml(TestCase):

    @staticmethod
    def get_metadata_xml(maintainers=(), local_use={}, longdescription=None):
        hs = ms = us = ls = ""
        if maintainers:
            ms = []
            for x in maintainers:
                ms.append("<email>%s</email>" % x[0])
                if len(x) > 1:
                    ms[-1] = "%s\n<name>%s</name>" % (ms[-1], x[1])
            ms = "<maintainer>%s</maintainer>\n" % \
                "</maintainer><maintainer>".join(ms)
        if local_use:
            us = ['<use>']
            for flag, desc in local_use.iteritems():
                us.append('<flag name="%s">%s</flag>' % (flag, desc))
            us.append('</use>')
            us = '\n'.join(us)
        if longdescription:
            ls = "<longdescription>%s</longdescription>\n" % longdescription
        s = \
"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE pkgmetadata SYSTEM "http://www.gentoo.org/dtd/metadata.dtd">
<pkgmetadata>
%s%s%s%s</pkgmetadata>""" % (hs, ms, us, ls)
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

    def test_local_use(self):
        # empty...
        self.assertEqual(dict(), self.get_metadata_xml().local_use)

        local_use = {
            "foo": "description for foo",
            "bar": "description for bar (<pkg>app-foo/bar</pkg> required)",
        }
        metadata_xml = self.get_metadata_xml(local_use=local_use)
        pkg_tag_re = re.compile(r'</?pkg>')
        local_use = dict(
                (k, pkg_tag_re.sub('', v))
                for k, v in local_use.iteritems())
        self.assertEqual(local_use, metadata_xml.local_use)

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
