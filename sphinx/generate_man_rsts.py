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

    def __init__(self, base_path):
        self.base_path = base_path

    positional_re = re.compile("(^|\n)([^: ]+)")
    positional_re = partial(positional_re.sub, '\g<1>:\g<2>:')

    def regen_if_needed(self, src, out_name=None):
        if out_name is None:
            out_name = src.rsplit(".")[-1]
        out_name += '.rst'
        out_path = pjoin(self.base_path, out_name)
        module = load_module(src)
        cur_time = int(os.stat(module.__file__).st_mtime)
        script_time = int(os.stat(__file__).st_mtime)
        cur_time = max([cur_time, script_time])
        try:
            trg_time = int(os.stat(out_path).st_mtime)
        except EnvironmentError, e:
            if e.errno != errno.ENOENT:
                raise
            trg_time = -1

        if cur_time != trg_time:
            sys.stdout.write("regenerating rst for %s\n" % (src,))
            data = self.generate_rst(src, module)
            open(out_path, "w").write("\n".join(data))

        os.chmod(out_path, 0644)
        os.utime(out_path, (cur_time, cur_time))

    @staticmethod
    def _get_formatter(parser, name):
        return argparse.RawTextHelpFormatter(name, width=1000)

    def process_positional(self, parser, name, action_group):
        l = []
        h = self._get_formatter(parser, name)
        h.add_arguments(action_group._group_actions)
        data = h.format_help().strip()
        if data:
            l.extend(_rst_header("=", action_group.title))
            if action_group.description:
                l.extend(description.split("\n"))
            l.extend(self.positional_re(data).split("\n"))
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
                continue
#               assert len(action_group._group_actions) == 1
#                l.extend(process_subparser(action_group, name))
            h = self._get_formatter(parser, name)
            #h.start_section(action_group.title)
            #h.add_text(action_group.description)
            h.add_arguments(action_group._group_actions)
            #h.end_section()
            data = h.format_help()
            if not data:
                continue
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

    def generate_rst(self, python_name, module):
        parser = module.argparse_parser
        return self.process_parser(parser, python_name.rsplit(".")[-1])

    def process_parser(self, parser, name):
        l = _rst_header('=', name, leading=True)

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
    converter = ManConverter(sys.argv[1])
    for x in sys.stdin:
        converter.regen_if_needed(*x.rstrip("\n").split())
