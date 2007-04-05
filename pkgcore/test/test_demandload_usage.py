# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2


import sys
from snakeoil.test import TestCase
from snakeoil import demandload

class TestDemandLoadTargets(TestCase):

    matching_types = [
        type(getattr(demandload, x)) for x in (
            "_replacer_from", "_replacer", "_importer", "_delayed_compiler")]

    def test_demandload_targets(self):
        # picks up only the namespace loaded for searching
        remaining = sys.modules.items()
        seen = set()
        while remaining:
            for name, mod in remaining:
                self.check_space(name, mod)
                seen.add(name)
            remaining = [
                (k, v) for k, v in sys.modules.iteritems() if k not in seen]

    def check_space(self, name, mod):
        if not name.startswith("pkgcore."):
            return
        for attr in dir(mod):
            try:
                obj = getattr(mod, attr)
                # force __getattribute__ to fire
                getattr(obj, "__class__", None)
            except ImportError:
                # hit one.
                self.fail("failed 'touching' demandloaded %s.%s" % (name, attr))
