#!/usr/bin/python
from snakeoil.modules import load_module
import datetime, os, errno
from pkgcore.util import argparse

def _rst_header(char, text, leading=False):
    s = char * len(text)
    if leading:
        return [s, text, s, '']
    return [text, s, '']

def _indent(stream):
    for s in stream:
        yield '  ' + s

def generate_usage(parser, name):
    h = argparse.RawTextHelpFormatter(name, width=1000)
    h.add_usage(parser.usage, parser._actions, parser._mutually_exclusive_groups)
    text = h.format_help()
    if text.startswith("usage:"):
        text = text[len("usage:"):].lstrip()
    return filter(None, text.split("\n"))

def process_action_groups(parser, name):
    l = []
    for action_group in parser._action_groups:
        if any(isinstance(x, argparse._SubParsersAction)
            for x in action_group._group_actions):
            continue
#            assert len(action_group._group_actions) == 1
#            l.extend(process_subparser(action_group, name))
        h = argparse.RawTextHelpFormatter(parser, name, width=1000)
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

def generate_rst(python_name, module):
    parser = module.argparse_parser
    return process_parser(parser, python_name.rsplit(".")[-1])

def process_parser(parser, name, author=None, copyright=None, version=None, section=1, group=None):
    l = _rst_header('=', name, leading=True)

#    description = parser.description
#    if description is None:
#        description = "%s command" % (name,)
#    l.extend(_rst_header('-', description, leading=True))
#    def _process_val(name, val):
#        if val:
#            l.append(":%s: %s" % (name, val))
#    _process_val("Author", author)
#    _process_val("Copyright", copyright)
#    _process_val("Version", version)
#    _process_val("Manual section", section)
#    _process_val("Manual group", group)
#    l.append(":Date: %s" % (datetime.datetime.now().strftime("%Y-%m-%d"),))
#    l += ['', '']

    l.extend(_rst_header('=', "synopsis"))
    l.extend(generate_usage(parser, name))
    l += ['']

    val = getattr(parser, 'long_description', parser.description)
    if val:
        l.extend(_rst_header("=", "DESCRIPTION"))
        l += [val, '']

    l.extend(process_action_groups(parser, name))

    return l

def regen_if_needed(src, out_path):
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
        data = generate_rst(src, module)
        open(out_path, "w").write("\n".join(data))

    os.chmod(out_path, 0644)
    os.utime(out_path, (cur_time, cur_time))

if __name__ == '__main__':
    import sys
    for x in sys.stdin:
        regen_if_needed(*x.rstrip("\n").split(" ", 1))
