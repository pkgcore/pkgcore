# Copyright: 2010 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD


from snakeoil.test import test_py3k_eq_hash_inheritance as module

class Test(module.Test):

    target_namespace = "pkgcore"
    ignore_all_import_failures = True
