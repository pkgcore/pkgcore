#!/usr/bin/env python

import argparse
import errno
import os
import subprocess

from snakeoil.dist.generate_man_rsts import ManConverter


def generate_man():
    print('Generating option and synopsis files for man pages')

    try:
        os.mkdir('generated')
    except OSError as e:
        if e.errno == errno.EEXIST:
            return
        raise

    bin_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bin')
    scripts = os.listdir(bin_path)

    # Note that filter-env is specially specified, since the command is installed
    # as 'filter-env', but due to python namespace contraints, it uses a '_'
    # instead.
    generated_man_pages = [
        ('pkgcore.scripts.' + s.replace('-', '_'), s) for s in scripts
    ]

    # generate man page option docs
    for module, script in generated_man_pages:
        os.symlink(os.path.join(os.pardir, 'generated', script), os.path.join('man', script))
        ManConverter.regen_if_needed('generated', module, out_name=script)


def generate_html():
    print('Generating API docs')
    subprocess.call(['sphinx-apidoc', '-Tef', '-o', 'api', '../pkgcore', '../pkgcore/test'])


if __name__ == '__main__':
    argparser = argparse.ArgumentParser(description='generate docs')
    argparser.add_argument('--man', action='store_true', help='generate man files')
    argparser.add_argument('--html', action='store_true', help='generate API files')

    opts = argparser.parse_args()

    # if run with no args, build all docs
    if not opts.man and not opts.html:
        opts.man = opts.html = True

    if opts.man:
        generate_man()

    if opts.html:
        generate_html()
