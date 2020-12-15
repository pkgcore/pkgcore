#!/usr/bin/env python3

"""Wrapper for running commandline scripts."""

import os
import sys
from importlib import import_module


def run(script_name):
    """Run a given script module."""
    try:
        from pkgcore.util.commandline import Tool
        script_module = '.'.join(
            os.path.realpath(__file__).split(os.path.sep)[-3:-1] +
            [script_name.replace('-', '_')])
        script = import_module(script_module)
    except ImportError as e:
        sys.stderr.write(f'Failed importing: {e}!\n')
        py_version = '.'.join(map(str, sys.version_info[:3]))
        sys.stderr.write(
            'Verify that pkgcore and its deps are properly installed '
            f'and/or PYTHONPATH is set correctly for python {py_version}.\n')
        # show traceback in debug mode or for unhandled exceptions
        if '--debug' in sys.argv[1:] or not all((e.__cause__, e.__context__)):
            sys.stderr.write('\n')
            raise
        sys.stderr.write('Add --debug to the commandline for a traceback.\n')
        sys.exit(1)

    tool = Tool(script.argparser)
    sys.exit(tool())


if __name__ == '__main__':
    # We're in a git repo or tarball so add the src dir to the system path.
    # Note that this assumes a certain module layout.
    src_dir = os.path.realpath(__file__).rsplit(os.path.sep, 3)[0]
    sys.path.insert(0, src_dir)
    run(os.path.basename(__file__))
