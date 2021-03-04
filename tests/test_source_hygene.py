from snakeoil.test.modules import ExportedModules


class Test_modules(ExportedModules):
    target_namespace = 'pkgcore'
    ignore_all_import_failures = True
