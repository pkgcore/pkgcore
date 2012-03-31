#!/usr/bin/python
import errno
import os
import re
import sys


def regenerate_if_needed(project, src, out):
    cut_off = int(max(os.stat(x).st_mtime for x in [src,__file__]))
    try:
        if int(os.stat(out).st_mtime) >= cut_off:
            return
    except EnvironmentError, e:
        if e.errno != errno.ENOENT:
            raise
    print "regenerating %s news for %s -> %s" % (project, src, out)
    new_text = convert_news(open(src, 'r').read(), project)
    open(out, 'w').write(new_text)
    os.utime(out, (-1, cut_off))


def convert_news(text, project_name):
    project_name = project_name.strip()
    def f(match):
        ver = match.group(1).strip()
        date = match.group(2)
        s = ' '.join([project_name, ver])
        if date is not None:
            s += ': %s' % (date.strip(),)
        # Ensure we leave a trailing and leading newline to keep ReST happy.
        l = ['', '.. _release-%s:' % (ver,), '', s, '-' * len(s), '']
        return '\n'.join(l)
    text = re.sub(r'(?:\n|^)%s +(0\.[^:\n]+):?([^\n]*)(?:\n|$)' % (project_name,),
        f, text)
    return ".. _news:\n\n%s" % (text,)


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print "wrong args given; need project_name src out"
        sys.exit(1)
    regenerate_if_needed(*sys.argv[1:4])
