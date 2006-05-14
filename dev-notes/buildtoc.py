#!/usr/bin/env python

"""Spit out a restructuredtext file linking to every .rst in cwd."""

import os,stat


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
		elif stat.S_ISDIR(os.stat(entry).st_mode):
			if os.path.exists(os.path.join(entry, "toc.rst")):
				print '- `%s <%s.html>`_' % (entry, "%s/toc.rst" % entry)

if __name__ == '__main__':
	main()
