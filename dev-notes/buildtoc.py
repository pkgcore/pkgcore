#!/usr/bin/env python

"""Spit out a restructuredtext file linking to every .rst in cwd."""

import os


def main():
	print '==================='
	print ' Table of contents '
	print '==================='
	print
	for entry in os.listdir(os.getcwd()):
		if entry == 'toc.rst':
			continue
		if entry.lower().endswith('.rst'):
			entry = entry[:-4]
			print '- `%s <%s.html>`_' % (entry, entry)


if __name__ == '__main__':
	main()
