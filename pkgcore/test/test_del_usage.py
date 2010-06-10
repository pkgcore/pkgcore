# Copyright: 2010 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD 3 clause

from snakeoil.test import test_del_usage as module

class Test(module.Test):

    target_namespace = "pkgcore"
    ignore_all_import_failures = True

