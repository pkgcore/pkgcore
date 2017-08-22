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

    argparser = getattr(script, 'argparser', None)
    tool = Tool(argparser)
    tool.main()


if __name__ == '__main__':
    # we're in a git repo or tarball so add the base dir to the system path
    repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, repo_dir)
    run(os.path.basename(__file__))
