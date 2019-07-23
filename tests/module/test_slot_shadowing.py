# Copyright: 2009 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

from snakeoil.test.slot_shadowing import SlotShadowing


class Test_slot_shadowing(SlotShadowing):

    target_namespace = "pkgcore"
    ignore_all_import_failures = True

    def _default_module_blacklister(self, target):
        return target in self.module_blacklist or target.startswith("pkgcore.test.")
