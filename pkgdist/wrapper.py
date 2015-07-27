#!/usr/bin/env python
# Copyright: 2015 Tim Harder <radhermit@gmail.com>
# License: BSD/GPL2

"""Wrapper script that messes with sys.path and runs scripts."""

from importlib import import_module
import os
import sys


def find_project():
    toplevel = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    toplevel_depth = len(toplevel.split('/'))

    # look for a top-level module that isn't pkgdist
    for root, dirs, files in os.walk(toplevel):
        if len(root.split('/')) > toplevel_depth + 1:
            continue
        if '__init__.py' in files and not \
                os.path.abspath(root).startswith(
                    os.path.dirname(os.path.realpath(__file__))):
            return os.path.basename(root)

    raise ValueError('No project module found')


project = find_project()


if __name__ == '__main__':
    # we're in a git repo or tarball so add the base dir to the system path
    sys.path.insert(1, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    try:
        scripts = import_module('%s.scripts' % os.path.basename(project))
    except ImportError:
        raise

    scripts.main(os.path.basename(__file__))
