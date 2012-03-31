#!/usr/bin/python
import errno
import os
import re
import sys


def regenerate_if_needed(project, src, out, release_extlink=None, git_extlink=None):
    cut_off = int(max(os.stat(x).st_mtime for x in [src,__file__]))
    try:
        if int(os.stat(out).st_mtime) >= cut_off:
            return
    except EnvironmentError, e:
        if e.errno != errno.ENOENT:
            raise
    print "regenerating %s news for %s -> %s" % (project, src, out)
    new_text = convert_news(open(src, 'r').read(), project, release_extlink, git_extlink)
    open(out, 'w').write(new_text)
    os.utime(out, (-1, cut_off))


def convert_news(text, project_name, release_extlink=None, git_extlink=None):
    project_name = project_name.strip()

    # First, escape all necessary characters so that since NEWS doesn't use true
    # ReST syntax.
    text = re.sub("\\\\", "\\\\", text)
    def f(match):
        return match.group(0).replace('_', '\_')
    #text = re.sub('((?:[^_]+_)+)(?=[;:.])', f, text)
    text = re.sub('_', '\\_', text)
    text = re.sub('(?<!\n)\*', '\\*', text)

    def f(match):
        ver = match.group(1).strip()
        date = match.group(2)
        s = ' '.join([project_name, ver])
        if date is not None:
            s += ': %s' % (date.strip(),)
        # Ensure we leave a trailing and leading newline to keep ReST happy.
        l = ['', '.. _release-%s:' % (ver,), '', s, '-' * len(s), '']

        l2 = []
        if release_extlink is not None:
            l2.append(':%s:`Download<%s>`' % (release_extlink, ver))
        if git_extlink is not None:
            l2.append(':%s:`Git history<%s>`' % (git_extlink, ver))

        if l2:
            l.append(', '.join(l2))
            l.append('')

        l.append('Notable changes:')
        l.append('')
        return '\n'.join(l)
    text = re.sub(r'(?:\n|^)%s +(0\.[^:\n]+):?([^\n]*)(?:\n|$)' % (project_name,),
        f, text)
    return ".. _news:\n\n%s" % (text,)


if __name__ == '__main__':
    if len(sys.argv) not in (4, 6):
        print "wrong args given; need project_name src out"
        sys.exit(1)
    regenerate_if_needed(*sys.argv[1:6])
