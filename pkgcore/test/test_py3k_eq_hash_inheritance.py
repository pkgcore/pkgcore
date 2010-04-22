# Copyright: 2010 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

try:
    from snakeoil.test import test_py3k_eq_hash_inheritance as module
except ImportError:
    # might seem ugly, but basically if we're running <snakeoil-0.3.6.4
    # which lacks this test, silence it
    class module(object):
        Test = object

class Test(module.Test):

    target_namespace = "pkgcore"
    ignore_all_import_failures = True
