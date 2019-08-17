from snakeoil.test.demandload import DemandLoadTargets
from snakeoil.test.modules import ExportedModules


class TestDemandLoadUsage(DemandLoadTargets):
    target_namespace = "pkgcore"
    ignore_all_import_failures = True


class Test_modules(ExportedModules):
    target_namespace = 'pkgcore'
    ignore_all_import_failures = True
