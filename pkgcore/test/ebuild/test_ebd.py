# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import subprocess
import sys

from snakeoil.osutils import pjoin

from pkgcore.ebuild import const
from pkgcore.test import TestCase

class Test_DontExportFuncsList(TestCase):
    base_path = const.EAPI_BIN_PATH

    def test_list_is_upto_date(self):

        with open(pjoin(self.base_path, "dont_export_funcs.list")) as f:
            existing = set(x.strip() for x in f)

        ppath = ":".join(sys.path)
        proc = subprocess.Popen([pjoin(self.base_path,
            "regenerate_dont_export_func_list.bash"), "-"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"PKGCORE_PYTHON_PATH":ppath},
            close_fds=True)

        self.assertEqual(proc.wait(), 0)
        current = set(x.strip().decode("ascii") for x in proc.stdout.read().split())

        missing = current.difference(existing)
        unneeded = existing.difference(current)

        stderr = proc.stderr.read()
        self.assertEqual(current, existing,
            msg="ondisk dont_export_funcs.list is out of date from the actual source"
                "\nmissing is %r\nuneeded is %r\nstderr was:\n%s" %
                (sorted(missing), sorted(unneeded), stderr))
