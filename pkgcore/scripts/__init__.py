# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

"""Commandline scripts.

Modules in here are accessible through the pwrapper script. They should have a
C{main} attribute that is a function usable with
:obj:`pkgcore.util.commandline.main` and use
:obj:`pkgcore.util.commandline.mk_argparser` (a wrapper around
C{ArgumentParser}) to handle argument parsing.

The goal of this is avoiding boilerplate and making sure the scripts have a
similar look and feel. If your script needs to do something
:obj:`pkgcore.util.commandline` does not support please improve it instead of
bypassing it.
"""
