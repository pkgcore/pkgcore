#!/usr/bin/env python

"""Wrapper for running commandline scripts."""

from importlib import import_module
import os
import sys


def run(script_name):
    """Run a given script module."""
    try:
        from pkgcore.util.commandline import Tool
        script_module = '.'.join(
            os.path.realpath(__file__).split(os.path.sep)[-3:-1] +
            [script_name.replace('-', '_')])
        script = import_module(script_module)
    except ImportError as e:
        sys.stderr.write('Failed importing: %s!\n' % str(e))
        sys.stderr.write(
            'Verify that pkgcore and its deps are properly installed '
            'and/or PYTHONPATH is set correctly for python %s.\n' %
            ('.'.join(map(str, sys.version_info[:3])),))
        if '--debug' in sys.argv:
            raise
        sys.stderr.write('Add --debug to the commandline for a traceback.\n')
        sys.exit(1)

    tool = Tool(script.argparser)
    ret = tool()
    raise SystemExit(ret)


if __name__ == '__main__':
    # we're in a git repo or tarball so add the base dir to the system path
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if not os.path.exists(os.path.join(repo_dir, 'setup.py')):
        raise SystemExit('unknown repo hierarchy, %r should be repo root' % repo_dir)
    sys.path.insert(0, repo_dir)
    run(os.path.basename(__file__))
