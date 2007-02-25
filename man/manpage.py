# Copyright: 2007 Brian Harring <ferringb@gmail.com>
# Copyright: ?-2006 Engelbert Gruber <grubert@users.sourceforge.net>
# Original Author: Englebert Gruber
# License: Public Domain

"""
Man page formatting for reStructuredText.

See http://www.tldp.org/HOWTO/Man-Page for a start.

Man pages have no subsection only parts.
Standard parts
  NAME ,
  SYNOPSIS ,
  DESCRIPTION ,
  OPTIONS ,
  FILES ,
  SEE ALSO ,
  BUGS ,
and
  AUTHOR .

"""

# NOTE: the macros only work when at line start, so try the rule
#       start new lines in visit_ functions.

__docformat__ = 'reStructuredText'

import sys
import os
import time
import re
from types import ListType

import docutils
from docutils import nodes, utils, writers, languages


class Writer(writers.Writer):

    supported = ('manpage')
    """Formats this writer supports."""

    output = None
    """Final translated form of `document`."""

    def __init__(self, debug_file):
        writers.Writer.__init__(self)
        self.translator_class = Translator
        self.debug_file = debug_file

    def translate(self):
        visitor = self.translator_class(self.document)
        if self.debug_file:
            open(self.debug_file, 'w').write(str(self.document))
        self.document.walkabout(visitor)
        self.output = visitor.astext()


class Table:
    def __init__(self):
        self._rows = []
        self._options = ['center', ]
        self._tab_char = '\t'
        self._coldefs = []
    def new_row(self):
        self._rows.append([])
    def append_cell(self, text):
        self._rows[-1].append(text)
        if len(self._coldefs) < len(self._rows[-1]):
            self._coldefs.append('l')
    def astext(self):
        text = '.TS\n'
        text += ' '.join(self._options) + ';\n'
        text += '|%s|.\n' % ('|'.join(self._coldefs))
        for row in self._rows:
            # row = array of cells. cell = array of lines.
            # line above 
            text += '_\n'
            nr_of_cells = len(row)
            ln_cnt = -1
            while ln_cnt < 10: # safety belt
                ln_cnt += 1
                line = []
                last_line = 1 
                for cell in row:
                    if len(cell) > ln_cnt:
                        line.append(cell[ln_cnt])
                        last_line = 0 
                    else:
                        line.append(" ")
                if last_line:
                    break
                text += self._tab_char.join(line) + '\n'
        text += '_\n'
        text += '.TE\n'
        return text

class Translator(nodes.NodeVisitor):
    """"""

    words_and_spaces = re.compile(r'\S+| +|\n')
    document_start = """Man page generated from reStructeredText."""


    def unimplemented_visit(self, node):
        raise NotImplementedError('visiting unimplemented node type: %s'
                                  % node.__class__.__name__)

    def noop(self, node):
        pass

    simple_defs = {
        'definition' : ('', ''),
        'definition_list' : ('', ''),
        'definition_list_item' : ('\n.TP', ''),
        'description' : ('\n', ''),
        'field_name' : ('\n.TP\n.B ', '\n'),
        'literal_block' : ('\n.nf\n', '\n.fi\n'),
        'option_list' : ('', ''),
        'option_list_item' : ('.TP', ''),
        'reference' : ('', ''),
        'strong' : ('\n.B ', ''),
        'term' : ('\n.B ', '\n'),
    }

    def f(mode, k, val):
        def f2(self, node):
            if val:
                self.body.append(val)
        return f2

    for k,v in simple_defs.iteritems():
        locals()['visit_%s' % k] = f('visit', k, v[0])
        locals()['depart_%s' % k] = f('depart', k, v[1])

    def __init__(self, document):
        nodes.NodeVisitor.__init__(self, document)
        self.settings = settings = document.settings
        lcode = settings.language_code
        self.language = languages.get_language(lcode)
        self.head = []
        self.body = []
        self.foot = []
        self.section_level = 0
        self.context = []
        self.topic_class = ''
        self.colspecs = []
        self.compact_p = 1
        self.compact_simple = None
        # the list style "*" bullet or "#" numbered
        self._list_char = []
        # writing the header .TH and .SH NAME is postboned after
        # docinfo.
        self._docinfo = {
                "title" : "", "subtitle" : "",
                "manual_section" : "", "manual_group" : "",
                "author" : "", 
                "date" : "", 
                "copyright" : "",
                "version" : "",
                    }
        self._in_docinfo = None
        self._active_table = None
        self._in_entry = None
        self.header_written = 0
        self.authors = []
        self.section_level = 0
        # central definition of simple processing rules
        # what to output on : visit, depart
        # TODO dont specify the newline before a dot-command, but ensure
        # check it is there.

    def comment_begin(self, text):
        """Return commented version of the passed text WITHOUT end of line/comment."""
        prefix = '\n.\\" '
        return prefix+prefix.join(text.split('\n'))

    def comment(self, text):
        """Return commented version of the passed text."""
        return self.comment_begin(text)+'\n'

    def astext(self):
        """Return the final formatted document as a string."""
        return ''.join(self.head + self.body + self.foot)

    def visit_Text(self, node):
        text = node.astext().replace('-','\-')
        text = text.replace("'","\\'")
        self.body.append(text)

    def list_start(self, node):
        class enum_char:
            enum_style = {
                    'arabic'     : (3,1),
                    'loweralpha' : (2,'a'),
                    'upperalpha' : (2,'A'),
                    'lowerroman' : (5,'i'),
                    'upperroman' : (5,'I'),
                    'bullet'     : (2,'\\(bu'),
                    'emdash'     : (2,'\\(em'),
                     }
            def __init__(self, style):
                self._style = self.enum_style[style]
                self._cnt = -1
            def next(self):
                self._cnt += 1
                try:
                    return "%d." % (self._style[1] + self._cnt)
                except:
                    if self._style[1][0] == '\\':
                        return self._style[1]
                    # BUG romans dont work
                    # BUG alpha only a...z
                    return "%c." % (ord(self._style[1])+self._cnt)
            def get_width(self):
                return self._style[0]

        if node.has_key('enumtype'):
            self._list_char.append(enum_char(node['enumtype']))
        else:
            self._list_char.append(enum_char('bullet'))
        if len(self._list_char) > 1:
            # indent nested lists
            # BUG indentation depends on indentation of parent list.
            self.body.append('\n.RS %d' % self._list_char[-2].get_width())

    def list_end(self):
        self._list_char.pop()
        if len(self._list_char) > 0:
            self.body.append('\n.RE\n')

    def append_header(self):
        """append header with .TH and .SH NAME"""
        # TODO before everything
        # .TH title section date source manual
        if self.header_written:
            return
        tmpl = (".TH %(title)s %(manual_section)s"
                " \"%(date)s\" \"%(version)s\" \"%(manual_group)s\"\n"
                ".SH NAME\n"
                "%(title)s \- %(subtitle)s\n")
        self.body.append(tmpl % self._docinfo)
        self.header_written = 1

    def visit_author(self, node):
        self._docinfo['author'] = node.astext()
        raise nodes.SkipNode

    def visit_authors(self, node):
        self.body.append(self.comment('visit_authors'))

    def depart_authors(self, node):
        self.body.append(self.comment('depart_authors'))

    def visit_block_quote(self, node):
        self.body.append(self.comment('visit_block_quote'))

    def depart_block_quote(self, node):
        self.body.append(self.comment('depart_block_quote'))

    def visit_bullet_list(self, node):
        self.list_start(node)

    def depart_bullet_list(self, node):
        self.list_end()

    def visit_colspec(self, node):
        self.colspecs.append(node)

    def write_colspecs(self):
        self.body.append("%s.\n" % ('L '*len(self.colspecs)))

    def visit_comment(self, node,
                      sub=re.compile('-(?=-)').sub):
        self.body.append(self.comment(node.astext()))
        raise nodes.SkipNode

    def visit_contact(self, node):
        self.visit_docinfo_item(node, 'contact')

    def depart_contact(self, node):
        self.depart_docinfo_item()

    def visit_copyright(self, node):
        self._docinfo['copyright'] = node.astext()
        raise nodes.SkipNode

    def visit_date(self, node):
        self._docinfo['date'] = node.astext()
        raise nodes.SkipNode

    visit_decoration = depart_decoration = noop

    def visit_docinfo(self, node):
        self._in_docinfo = 1

    def depart_docinfo(self, node):
        self._in_docinfo = None
        # TODO nothing should be written before this
        self.append_header()

    def visit_docinfo_item(self, node, name):
        self.body.append(self.comment('%s: ' % self.language.labels[name]))
        if len(node):
            return
            if isinstance(node[0], nodes.Element):
                node[0].set_class('first')
            if isinstance(node[0], nodes.Element):
                node[-1].set_class('last')

    def visit_document(self, node):
        self.body.append(self.comment(self.document_start))
        # writing header is postboned
        self.header_written = 0

    def depart_document(self, node):
        if self._docinfo['author']:
            self.body.append('\n.SH AUTHOR\n%s\n' 
                    % self._docinfo['author'])
        if self._docinfo['copyright']:
            self.body.append('\n.SH COPYRIGHT\n%s\n' 
                    % self._docinfo['copyright'])
        self.body.append(
                self.comment(
                        'Generated by docutils manpage writer on %s.\n' 
                        % (time.strftime('%Y-%m-%d %H:%M')) ) )

    def visit_emphasis(self, node):
        self.body.append('\n.I ')

    def depart_emphasis(self, node):
        self.body.append('\n')

    def visit_enumerated_list(self, node):
        self.list_start(node)

    def depart_enumerated_list(self, node):
        self.list_end()

    visit_field = depart_field = noop

    def visit_field_body(self, node):
        if self._in_docinfo:
            self._docinfo[
                    self._field_name.lower().replace(" ","_")] = node.astext()
            raise nodes.SkipNode

    def depart_field_body(self, node):
        self.body.append(self.comment('depart_field_body'))

    def visit_field_list(self, node):
        self.body.append(self.comment('visit_field_list'))

    def depart_field_list(self, node):
        self.body.append(self.comment('depart_field_list'))

    def visit_field_name(self, node):
        if self._in_docinfo:
            self._field_name = node.astext()
            raise nodes.SkipNode
        else:
            self.body.append(self.simple_defs['field_name'][0])

    def depart_field_name(self, node):
        self.body.append(self.simple_defs['field_name'][1])

    visit_generated = depart_generated = noop

    def visit_line_block(self, node):
        self.body.append('\n')

    def depart_line_block(self, node):
        self.body.append('\n')

    def visit_list_item(self, node):
        self.body.append('\n.TP %d\n%s' % (
                self._list_char[-1].get_width(),
                self._list_char[-1].next(),) )

    def visit_option(self, node):
        # each form of the option will be presented separately
        if self.context[-1]>0:
            self.body.append(', ')
        if self.context[-3] == '.BI':
            self.body.append('\\')
        self.body.append(' ')

    def depart_option(self, node):
        self.context[-1] += 1

    def visit_option_group(self, node):
        # as one option could have several forms it is a group
        # options without parameter bold only, .B, -v
        # options with parameter bold italic, .BI, -f file
        
        # we do not know if .B or .BI
        self.context.append('.B')           # blind guess
        self.context.append(len(self.body)) # to be able to insert later
        self.context.append(0)              # option counter

    def depart_option_group(self, node):
        self.context.pop()  # the counter
        start_position = self.context.pop()
        text = self.body[start_position:]
        del self.body[start_position:]
        self.body.append('\n%s%s' % (self.context.pop(), ''.join(text)))

    visit_option_string = depart_option_string = noop

    def visit_option_argument(self, node):
        self.context[-3] = '.BI'
        if self.body[len(self.body)-1].endswith('='):
            # a blank only means no blank in output
            self.body.append(' ')
        else:
            # backslash blank blank
            self.body.append('\\  ')

    def depart_paragraph(self, node):
        # TODO .PP or an empty line
        if self.body and not self.body[-1].endswith("\n"):
            self.body.append('\n')

    def visit_raw(self, node):
        if node.get('format') == 'manpage':
            self.body.append(node.astext())
        # Keep non-HTML raw text out of output:
        raise nodes.SkipNode

    def visit_revision(self, node):
        self.visit_docinfo_item(node, 'revision')

    def depart_revision(self, node):
        self.depart_docinfo_item()

    def visit_row(self, node):
        self._active_table.new_row()

    def visit_section(self, node):
        self.section_level += 1

    def depart_section(self, node):
        self.section_level -= 1

    def visit_substitution_definition(self, node):
        """Internal only."""
        raise nodes.SkipNode

    def visit_substitution_reference(self, node):
        self.unimplemented_visit(node)

    def visit_subtitle(self, node):
        self._docinfo["subtitle"] = node.astext()
        raise nodes.SkipNode

    def visit_system_message(self, node):
        # TODO add report_level
        #if node['level'] < self.document.reporter['writer'].report_level:
            # Level is too low to display:
        #    raise nodes.SkipNode
        self.body.append('\.SH system-message\n')
        attr = {}
        backref_text = ''
        if node.hasattr('id'):
            attr['name'] = node['id']
        if node.hasattr('line'):
            line = ', line %s' % node['line']
        else:
            line = ''
        self.body.append('System Message: %s/%s (%s:%s)\n'
                         % (node['type'], node['level'], node['source'], line))

    def depart_system_message(self, node):
        self.body.append('\n')

    def visit_table(self, node):
        self._active_table = Table()

    def depart_table(self, node):
        self.body.append(self._active_table.astext())
        self._active_table = None

    def visit_target(self, node):
        self.body.append(self.comment('visit_target'))

    def depart_target(self, node):
        self.body.append(self.comment('depart_target'))

    visit_tbody = depart_tbody = noop
    visit_tgroup = depart_tgroup = noop

    def visit_title(self, node):
        if len(self.body) and not self.body[-1].endswith("\n"):
            self.body.append("\n")
        if isinstance(node.parent, nodes.topic):
            self.body.append(self.comment('topic-title'))
        elif isinstance(node.parent, nodes.sidebar):
            self.body.append(self.comment('sidebar-title'))
        elif isinstance(node.parent, nodes.admonition):
            self.body.append(self.comment('admonition-title'))
        elif self.section_level == 0:
            # document title for .TH
            self._docinfo['title'] = node.astext()
            raise nodes.SkipNode
        elif self.section_level == 1:
            self.body.append('.SH ')
        else:
            self.body.append('.SS ')

    def depart_title(self, node):
        if not self.body[-1].endswith("\n"):
            self.body.append('\n')

    def visit_topic(self, node):
        self.body.append(self.comment('topic: '+node.astext()))
        raise nodes.SkipNode
        ##self.topic_class = node.get('class')

    def visit_transition(self, node):
        # .PP      Begin a new paragraph and reset prevailing indent.
        # .sp N    leaves N lines of blank space.
        # .ce      centers the next line
        self.body.append('\n.sp\n.ce\n----\n')

    def depart_transition(self, node):
        self.body.append('\n.ce 0\n.sp\n')

    def visit_version(self, node):
        self._docinfo["version"] = node.astext()
        raise nodes.SkipNode

    def __getattr__(self, attr):
        if attr.startswith("visit_"):
            if not hasattr(self, "depart_%s" % attr[6:]):
                obj = self.unimplemented_visit
            else:
                obj = self.noop
        elif attr.startswith("depart_"):
            if not hasattr(self, "visit_%s" % attr[6:]):
                obj = self.unimplemented_visit
            else:
                obj = self.noop
        else:
            raise AttributeError(self, attr)
        setattr(self, attr, obj)
        return obj

# vim: set et ts=4 ai :
