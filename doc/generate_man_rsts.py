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

_splitting_regex = re.compile("(?:^|\n+(?=[^ \n]))")
def _find_spacing(string):
  pre, sep, post = string.rpartition('  ')
  while pre:
    yield len(pre)
    pre, sep, post = pre.rpartition('  ')

def _deserialize_2d_array(data):
    lines = _splitting_regex.split(data.strip())
    if not lines:
        return []
    line_iter = iter(lines)
    candidates = set(_find_spacing(line_iter.next()))
    for line in lines:
        candidates.intersection_update(_find_spacing(line))
        if not candidates:
            break
    else:
        lowest = min(candidates)
        return [(line[:lowest].strip(), line[lowest+2:].strip())
            for line in lines]
    raise Exception("Failed to parse %r" % (data,))


class ManConverter(object):

    positional_re = re.compile("(^|\n)([^: ]+)")
    positional_re = partial(positional_re.sub, '\g<1>:\g<2>:')

    arg_enumeration_re = re.compile("{([^}]+)}")
    def _rewrite_option(self, text):
        def f(match):
            string = match.group(1)
            string = string.replace(',', '|')
            array = [x.strip() for x in string.split('|')]
            # Specifically return '|' w/out spaces; later code is
            # space sensitve.  We do the appropriate replacement as
            # the last step.
            return '<%s>' % ('|'.join(array),)
        text = self.arg_enumeration_re.sub(f, text)
        # Now that we've convert {x,y} style options, we need to next
        # convert multi-argument options into a form that is parsable
        # as a two item tuple.
        l = []
        for chunk in text.split(','):
            chunk = chunk.split()
            if len(chunk) > 2:
                chunk[1:] = ['<%s>' % ' '.join(chunk[1:])]
            if not chunk[0].startswith('-'):
                chunk[0] = ':%s:' % (chunk[0],)
            l.append(' '.join(chunk))
        # Recompose the options into one text field.
        text = ', '.join(l)
        # Finally, touch up <x|a> into <x | a>
        return text.replace('|', ' | ')

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
            cls(base_path, out_name, module.argparser, mtime=cur_time).run()

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
        try:
            return self.process_parser(parser, python_name.rsplit(".")[-1])
        finally:
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
            base = pjoin(self.base_path, '%s-subcommands' % (self.name,))
            try:
                os.mkdir(base)
            except EnvironmentError, e:
                if e.errno != errno.EEXIST:
                    raise
            for subcommand, parser in action_group._group_actions[0].choices.iteritems():
                self.__class__(base, "%s %s" % (self.name, subcommand), parser, mtime=self.mtime,
                    out_name=subcommand).run()
            l.append('')
            l.append(".. toctree::")
            l.append("   :maxdepth: 2")
            l.append('')
            l.extend("   %s %s <%s-subcommands/%s>" % ((name, subcommand)*2) for subcommand in action_group._group_actions[0].choices)
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
            l.extend(_rst_header("=", action_group.title))
            if action_group.description:
                l.extend(action_group.description.lstrip('\n').rstrip('\n').splitlines())
                l.append('')

            array = _deserialize_2d_array(data)
            if array:
                array = [(self._rewrite_option(x[0]), x[1]) for x in array]
                min_length = max(len(x[0]) for x in array) +2
                array = [(x[0].ljust(min_length, ' '), x[1]) for x in array]
                l.extend(''.join(x) for x in array)
            l.append('')
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
    output = sys.argv[1]
    targets = sys.argv[2:]
    if not targets:
        sys.exit(0)
    elif targets[0] == '--conf':
        import conf
        targets = getattr(conf, 'generated_man_pages', [])
    elif len(targets) % 2 != 0:
        print "bad arguments given"
        sys.exit(1)
    else:
        targets = iter(targets)
        targets = zip(targets, targets)
    output = os.path.abspath(output)
    if not os.path.isdir(output):
        os.makedirs(output)
    for source, target in targets:
        ManConverter.regen_if_needed(sys.argv[1], source, target)
