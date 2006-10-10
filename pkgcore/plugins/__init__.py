# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""pkgcore plugins package."""


import os
import sys

__path__ = list(
    os.path.abspath(os.path.join(path, 'pkgcore', 'plugins'))
    for path in sys.path)
