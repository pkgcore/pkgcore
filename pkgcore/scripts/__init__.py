# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: BSD/GPL2

"""Commandline scripts.

Modules in here are accessible through the pwrapper script. They
should have an C{OptionParser} attribute that is a
L{snakeoil.commandline.OptionParser} subclass and a C{main}
attribute that is a function usable with
L{snakeoil.commandline.main}.

The goal of this is avoiding boilerplate and making sure the scripts
have a similar look and feel. If your script needs to do something
L{snakeoil.commandline} does not support please improve it instead
of bypassing it.
"""
