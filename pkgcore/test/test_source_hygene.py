# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD


from snakeoil.test import test_demandload_usage
from snakeoil.test import test_source_hygene

class TestDemandLoadUsage(test_demandload_usage.TestDemandLoadTargets):
    target_namespace = "pkgcore"
    ignore_all_import_failures = True

class Test_modules(test_source_hygene.Test_modules):
    target_namespace = 'pkgcore'
    ignore_all_import_failures = True
