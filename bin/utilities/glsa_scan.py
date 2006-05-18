#!/usr/bin/python
import time
from pkgcore.pkgsets.glsa import GlsaDirSet
from pkgcore.config import load_config
r = load_config().repo["rsync repo"]
start_time = time.time()
for a in GlsaDirSet(r, None):
	l=r.match(a)
	if l:
		print "\n%s\naffected:   %s" % (a, ", ".join(str(x) for x in sorted(l)))
		print "available:  %s\n" % ", ".join(str(x) for x in sorted(r.itermatch(a[0])))
print "spent %.2f seconds loading/searching" % (time.time() - start_time)
