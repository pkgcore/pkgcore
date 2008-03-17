#!/usr/bin/env python


"""Script for rebuilding our documentation."""


import sys
import os.path
import optparse

from docutils import nodes, core
from docutils.parsers import rst
import docutils.utils

sys.path.append('man')
import manpage

from snakeoil import modules

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
trac.arguments = (1, 1, True)
trac.options = None
trac.content = False
rst.directives.register_directive('trac', trac)
rst.roles.register_local_role('trac', trac_role)


class HelpFormatter(optparse.HelpFormatter):

    """Hack to "format" optparse help as a docutils tree.

    Normally the methods return strings that are glued together. This
    one builds a docutils tree as its "result" attribute and returns
    empty strings.
    """

    def __init__(self, state):
        optparse.HelpFormatter.__init__(
            self, indent_increment=0, max_help_position=24, width=80,
            short_first=0)
        self.result = nodes.paragraph()
        self.current = nodes.option_list()
        self.result += self.current
        self._state = state

    def format_heading(self, heading):
        section = nodes.section()
        self.result += section
        section += nodes.title(text=heading)
        self.current = nodes.option_list()
        section += self.current
        return ''

    def format_option(self, option):
        item = nodes.option_list_item()
        group = nodes.option_group()
        item.append(group)
        for opt_string in self.option_strings[option]:
            opt_node = nodes.option()
            opt_node.append(nodes.option_string(text=opt_string))
            if option.takes_value():
                metavar = option.metavar or option.dest
                opt_node.append(nodes.option_argument(text=metavar))
            group.append(opt_node)
        if option.long_help:
            desc = nodes.description()
            par = nodes.paragraph()
            helpnodes, messages = self._state.inline_text(option.long_help, 0)
            par.extend(helpnodes)
            # XXX I have no idea if this makes sense and triggering it
            # without making rst2man explode is nontrivial.
            par.extend(messages)
            desc.append(par)
            group.append(desc)
        elif option.help:
            desc = nodes.description()
            par = nodes.paragraph(text=option.help)
            desc.append(par)
            group.append(desc)
        self.current.append(item)
        return ''

    def format_option_strings(self, option):
        return option._short_opts + option._long_opts

def script_options(name, arguments, options, content, lineno,
                   content_offset, block_text, state, state_machine):
    assert len(arguments) == 1
    assert not options, options
    parserclass = modules.load_attribute(arguments[0])
    if isinstance(parserclass, dict):
        comp = nodes.compound()
        base = arguments[0].split(".")[-2] # script location.
        for command_name, bits in sorted(parserclass.iteritems()):
            comp += nodes.title(text="%s %s" % (base, command_name))
            comp += generate_script(bits[0], state)
        return comp
    return generate_script(parserclass, state)
            

def generate_script(parserclass, state):
    optionparser = parserclass()
    formatter = HelpFormatter(state)
    optionparser.format_help(formatter)
    return formatter.result

# 1 argument, no optional arguments, no spaces in the argument.
script_options.arguments = (1, 0, False)
# No options.
script_options.options = None
# No content used.
script_options.content = False

rst.directives.register_directive('pkgcore_script_options', script_options)


def process_docs(directory, force, do_parent=False):
    """Generate the table of contents and html files."""
    print 'processing %s' % (directory,)
    # Dirs first so we pick up their contents when generating ours.
    for child in os.listdir(directory):
        target = os.path.join(directory, child)
        if os.path.isdir(target):
            process_docs(target, force, True)
    # Write the table of contents .rst file while processing files.
    indexpath = os.path.join(directory, 'index.rst')
    out = open(indexpath, 'w')
    try:
        out.write('===================\n')
        out.write(' Table of contents\n')
        out.write('===================\n')
        out.write('\n')
        if do_parent:
            out.write('- `../ <../index.html>`_\n')
        for entry in sorted(os.listdir(directory)):
            original = os.path.join(directory, entry)
            if entry == 'index.rst':
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
                  os.path.exists(os.path.join(original, 'index.rst'))):
                out.write('- `%s/ <%s/index.html>`_\n' % (entry, entry))
    finally:
        out.close()
    # And convert the index.
    # (Guess we could keep its rst only in memory but who knows, someone
    # might want to read it!)
    core.publish_file(source_path=indexpath,
                      destination_path=os.path.join(directory, 'index.html'),
                      writer_name='html')


def process_man(directory, force, debug):
    """Generate manpages."""
    print 'processing %s' % (directory,)
    debug_loc = None
    for entry in os.listdir(directory):
        original = os.path.join(directory, entry)
        if entry.lower().endswith('rst'):
            base = entry[:-4]
            target = os.path.join(directory, base)
            if debug:
                debug_loc = os.path.join(directory, base) + '.doctree'
            if force or not os.path.exists(target) or (
                os.path.getmtime(target) < os.path.getmtime(original)):
                print 'writing %s' % (target,)
                core.publish_file(source_path=original,
                                  destination_path=target,
                                  writer=manpage.Writer(debug_loc))
            else:
                print 'up to date: %s' % (target,)


if __name__ == '__main__':
    print 'checking documentation, use --force to force rebuild'
    print
    force = '--force' in sys.argv
    debug = '--debug' in sys.argv
    for directory in ['dev-notes', 'doc']:
        process_docs(os.path.join(os.path.dirname(__file__), directory), force)
    process_man(os.path.join(os.path.dirname(__file__), 'man'), force, debug)
