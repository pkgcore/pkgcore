#!/usr/bin/python
from snakeoil.modules import load_module
import datetime, os, errno, re
from pkgcore.util import argparse
pjoin = os.path.join
from snakeoil.currying import partial

def _rst_header(char, text, leading=False):
    s = char * len(text)
    if leading:
        return [s, text, s, '']
    return [text, s, '']

def _indent(stream):
    for s in stream:
        yield '  ' + s


class ManConverter(object):

    positional_re = re.compile("(^|\n)([^: ]+)")
    positional_re = partial(positional_re.sub, '\g<1>:\g<2>:')

    option_list_re = re.compile("(^|\n)(?!`)(?:-{1,2})(.*?)  ")
    def mangle_options(match):
        text = raw_text = match.string[match.start():match.end()]
        leading = ''
        if raw_text[0] == '\n':
            leading = '\n'
            text = raw_text[1:]
        if '\n' in text:
            # bad match...
            print "not rewriting %r" % (text,)
            return raw_text
        text = text.split(',')
        l = []
        for chunk in text:
            chunk = chunk.split()
            if len(chunk) > 2:
                chunk[1:] = ['<%s>' % (' '.join(chunk[1:]),)]
            l.append(' '.join(chunk))
        return "%s%s  " % (leading, ', '.join(l))

    option_list_re = partial(option_list_re.sub,
        mangle_options)
    mangle_options = staticmethod(mangle_options)

    @classmethod
    def regen_if_needed(cls, base_path, src, out_name=None, force=False):
        if out_name is None:
            out_name = src.rsplit(".", 1)[-1]
        out_path = pjoin(base_path, '%s.rst' % (out_name,))
        script_time = int(os.stat(__file__).st_mtime)
        module = load_module(src)
        cur_time = int(os.stat(module.__file__).st_mtime)
        cur_time = max([cur_time, script_time])
        try:
            trg_time = int(os.stat(out_path).st_mtime)
        except EnvironmentError, e:
            if e.errno != errno.ENOENT:
                raise
            trg_time = -1

        if cur_time != trg_time or force:
            cls(base_path, out_name, module.argparse_parser, mtime=cur_time).run()

    def __init__(self, base_path, name, parser, mtime=None, out_name=None):
        self.see_also = []
        self.subcommands_to_generate = []
        self.base_path = base_path
        if out_name is None:
            out_name = name
        self.out_name = out_name
        self.out_path = pjoin(base_path, out_name + '.rst')
        self.name = name
        self.parser = parser
        self.mtime = mtime

    def run(self, mtime=None):
        if mtime is None:
            mtime = self.mtime
        sys.stdout.write("regenerating rst for %s\n" % (self.name,))
        data = self.generate_rst(self.name, self.parser)
        open(self.out_path, "w").write("\n".join(data))

        os.chmod(self.out_path, 0644)
        if mtime:
            os.utime(self.out_path, (mtime, mtime))

    def generate_rst(self, python_name, parser):
        self.see_also = []
        self.subcommands_generate = []
        try:
            return self.process_parser(parser, python_name.rsplit(".")[-1])
        finally:
            for x in self.subcommands_generate:
                name = python_name + '-' + x[0]
                self.regen_if_needed(python_name, out_name=name, force=True, parser=x[1])
            self.subcommands_generate = []
            self.see_also = []

    @staticmethod
    def _get_formatter(parser, name):
        return argparse.RawTextHelpFormatter(name, width=1000,
            max_help_position=1000)

    def process_positional(self, parser, name, action_group):
        l = []
        h = self._get_formatter(parser, name)
        h.add_arguments(action_group._group_actions)
        data = h.format_help().strip()
        if data:
            l.extend(_rst_header("=", action_group.title))
            if action_group.description:
                l.extend(action_group.description.split("\n"))
            l.extend(self.positional_re(data).split("\n"))
            l.append('')
        return l

    def process_subcommands(self, parser, name, action_group):
        l = []
        h = self._get_formatter(parser, name)
        h.add_arguments(action_group._group_actions)
        data = h.format_help().strip()
        if data:
            assert len(action_group._group_actions) == 1
            l.extend(_rst_header("=", action_group.title))
            if action_group.description:
                l.extend(action_group.description.split("\n"))
            #data = re.sub("(^|\n)\{[^\}]+\}($|\n)", "\g<1>\g<2>", data)
            #data = re.sub("(^|\n)  ([^ ]+) +([^\n]+)",
            #    "\g<1>:doc:`%s-\g<2>`:  \g<3>" % (name,), data)
            for subcommand, parser in action_group._group_actions[0].choices.iteritems():
                self.__class__(self.base_path, "%s %s" % (self.name, subcommand), parser, mtime=self.mtime,
                    out_name="%s-%s" % (self.out_name, subcommand)).run()
            l.append('')
            l.append(".. toctree::")
            l.append("   :maxdepth: 2")
            l.append('')
            l.extend("   %s %s <%s-%s>" % ((name, subcommand)*2) for subcommand in action_group._group_actions[0].choices)
            l.append('')
            #l.extend(data.split("\n"))
            l.append('')
        return l

    def process_action_groups(self, parser, name):
        l = []
        for action_group in parser._action_groups:
            if getattr(action_group, 'marker', '') == 'positional' or \
                action_group.title == 'positional arguments':
                l.extend(self.process_positional(parser, name, action_group))
                continue
            if any(isinstance(x, argparse._SubParsersAction)
                for x in action_group._group_actions):
                assert len(action_group._group_actions) == 1
                l.extend(self.process_subcommands(parser, name, action_group))
                continue
            h = self._get_formatter(parser, name)
            #h.start_section(action_group.title)
            #h.add_text(action_group.description)
            h.add_arguments(action_group._group_actions)
            #h.end_section()
            data = h.format_help()
            if not data:
                continue
            data = self.option_list_re(data)
            l.extend(_rst_header("=", action_group.title))
            if action_group.description:
                l.extend(action_group.description.split("\n"))
            l.extend(data.split("\n"))
        return l

    def generate_usage(self, parser, name):
        h = self._get_formatter(parser, name)
        h.add_usage(parser.usage, parser._actions, parser._mutually_exclusive_groups)
        text = h.format_help()
        if text.startswith("usage:"):
            text = text[len("usage:"):].lstrip()
        return filter(None, text.split("\n"))

    def process_parser(self, parser, name):
        l = ['.. _`%s manpage`:' % (name,), '']
        l.extend(_rst_header('=', name, leading=True))

        l.extend(_rst_header('=', "synopsis"))
        l.extend(self.generate_usage(parser, name))
        l += ['']

        val = getattr(parser, 'long_description', parser.description)
        if val:
            l.extend(_rst_header("=", "DESCRIPTION"))
            l += [val, '']

        l.extend(self.process_action_groups(parser, name))

        return l

if __name__ == '__main__':
    import sys
    for x in sys.stdin:
        ManConverter.regen_if_needed(sys.argv[1], *x.rstrip("\n").split())
