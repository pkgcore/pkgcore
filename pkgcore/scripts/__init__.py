#!/usr/bin/env python
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

"""Commandline scripts.

Scripts in here are accessible through this module. They should have a C{main}
attribute that is a function usable with :obj:`pkgcore.util.commandline.main`
and use an :obj:`pkgcore.util.commandline.ArgumentParser` instance to handle
argument parsing.

The goal of this is avoiding boilerplate and making sure the scripts have a
similar look and feel. If your script needs to do something
:obj:`pkgcore.util.commandline` does not support please improve it instead of
bypassing it.
"""

from importlib import import_module
import os
import sys


def main(script_name):
    try:
        from pkgcore.util import commandline
        script_module = '.'.join(
            os.path.realpath(__file__).split('/')[-3:-1] +
            [script_name.replace('-', '_')])
        script = import_module(script_module)
    except ImportError as e:
        sys.stderr.write('Failed importing: %s!\n' % str(e))
        sys.stderr.write(
            'Verify that snakeoil and pkgcore are properly installed '
            'and/or PYTHONPATH is set correctly for python %s.\n' %
            ('.'.join(map(str, sys.version_info[:3])),))
        if '--debug' in sys.argv:
            raise
        sys.stderr.write('Add --debug to the commandline for a traceback.\n')
        sys.exit(1)

    argparser = getattr(script, 'argparser', None)
    commandline.main(argparser)


if __name__ == '__main__':
    # we're in a git repo or tarball so add the base dir to the system path
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main(os.path.basename(__file__))
