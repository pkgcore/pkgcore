#!/usr/bin/env python


"""Script for rebuilding our documentation."""


import sys
import os.path

from docutils import nodes, core
from docutils.parsers import rst


# (limited) support for trac wiki links.
# This is copied and hacked up from rst.py in the trac source.

def trac_get_reference(rawtext, link, text):
    if not link.startswith('rst:'):
        return None
    target = link.split(':', 1)[1]
    reference = nodes.reference(rawtext, text or target)
    reference['refuri'] = target
    return reference

def trac(name, arguments, options, content, lineno,
         content_offset, block_text, state, state_machine):
    """Inserts a `reference` node into the document 
    for a given `TracLink`_, based on the content 
    of the arguments.

    Usage::

      .. trac:: target [text]

    ``target`` may be any `TracLink`_, provided it doesn't
    embed a space character (e.g. wiki:"..." notation won't work).

    ``[text]`` is optional.  If not given, ``target`` is
    used as the reference text.

    .. _TracLink: http://trac.edgewall.org/wiki/TracLinks
    """
    link = arguments[0]
    if len(arguments) == 2:
        text = arguments[1]
    else:
        text = None
    reference = trac_get_reference(block_text, link, text)
    if reference:
        p = nodes.paragraph()
        p += reference
        return p
    # didn't find a match (invalid TracLink),
    # report a warning
    warning = state_machine.reporter.warning(
            '%s is not a valid TracLink' % (arguments[0]),
            nodes.literal_block(block_text, block_text),
            line=lineno)
    return [warning]

def trac_role(name, rawtext, text, lineno, inliner, options={},
              content=[]):
    args  = text.split(" ",1)
    link = args[0]
    if len(args)==2:
        text = args[1]
    else:
        text = None
    reference = trac_get_reference(rawtext, link, text)
    if reference:
        return [reference], []
    warning = nodes.warning(None, nodes.literal_block(text,
        'WARNING: %s is not a valid TracLink' % rawtext))
    return warning, []

# 1 required arg, 1 optional arg, spaces allowed in last arg
trac.arguments = (1,1,1)
trac.options = None
trac.content = None
rst.directives.register_directive('trac', trac)
rst.roles.register_local_role('trac', trac_role)


"""Spit out a restructuredtext file linking to every .rst in cwd."""


def process(directory, force):
    """Generate the table of contents and html files."""
    print 'processing %s' % (directory,)
    # Dirs first so we pick up their contents when generating ours.
    for child in os.listdir(directory):
        target = os.path.join(directory, child)
        if os.path.isdir(target):
            process(target, force)
    # Write the table of contents .rst file while processing files.
    tocpath = os.path.join(directory, 'toc.rst')
    out = open(tocpath, 'w')
    try:
        out.write('===================\n')
        out.write(' Table of contents\n')
        out.write('===================\n')
        out.write('\n')
        for entry in os.listdir(directory):
            original = os.path.join(directory, entry)
            if entry == 'toc.rst':
                continue
            if entry.lower().endswith('.rst'):
                base = entry[:-4]
                target = os.path.join(directory, base) + '.html'
                out.write('- `%s <%s.html>`_\n' % (base, base))
                # Check if we need to reprocess.
                if force or not os.path.exists(target) or (
                    os.path.getmtime(target) < os.path.getmtime(original)):
                    print 'writing %s' % (target,)
                    core.publish_file(source_path=original,
                                      destination_path=target,
                                      writer_name='html')
                else:
                    print 'up to date: %s' % (target,)
            elif (os.path.isdir(original) and
                  os.path.exists(os.path.join(original, 'toc.rst'))):
                out.write('- `%s <%s.html>`_\n' %
                          (entry, "%s/toc.rst" % entry))
    finally:
        out.close()
    # And convert the toc.
    # (Guess we could keep the toc rst only in memory but who knows, someone
    # might want to read it!)
    core.publish_file(source_path=tocpath,
                      destination_path=os.path.join(directory, 'toc.html'),
                      writer_name='html')


if __name__ == '__main__':
    print 'checking documentation, use --force to force rebuild'
    print
    force = '--force' in sys.argv
    for directory in ['dev-notes', 'doc']:
        process(os.path.join(os.path.dirname(__file__), directory), force)
