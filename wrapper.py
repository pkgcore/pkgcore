#!/usr/bin/env python
# Copyright: 2015 Tim Harder <radhermit@gmail.com>
# License: BSD/GPL2

"""Wrapper script that messes with sys.path and runs scripts."""

from importlib import import_module
import os
import sys

if __name__ == '__main__':
    # we're in a git repo or tarball so add the base dir to the system path
    repo_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(1, repo_path)

    try:
        scripts = import_module('%s.scripts' % os.path.basename(repo_path))
    except ImportError as e:
        raise

    scripts.main(os.path.basename(__file__))
