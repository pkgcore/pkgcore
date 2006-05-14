#!/usr/bin/python
import threading, Queue
import sys
import time
from pkgcore.config import load_config

def regen_iter(iterable):
	for x in iterable:
		try:
			x.keywords
		except RuntimeError:
			raise
		except Exception, e:
			print "caught exception %s for %s" % (e, x)

def reclaim_threads(threads):
	for x in threads:
		try:
			x.join()
		except RuntimeError:
			raise
		except Exception, e:
			print "caught exception %s reclaiming thread" % e


if __name__ == "__main__":
	if len(sys.argv) > 2:
		print "need a single optional arg, # of threads to spawn"
		sys.exit(1)
	elif len(sys.argv) == 2:
		try:
			thread_count = int(sys.argv[1])
			if thread_count < 1:
				raise ValueError
		except ValueError:
			print "arg must be an integer, and greater then 0"
			sys.exit(1)
	else:
		thread_count = 1
	repo = load_config().repo["rsync repo"]
	start_time = time.time()
	count = 0
	if thread_count == 1:
		def passthru(iterable):
			global count
			for x in iterable:
				count += 1
				yield x
		regen_iter(passthru(repo))
	else:
		queue = Queue.Queue(thread_count*2)
		kill = threading.Event()
		kill.clear()
		def iter_queue(kill, qlist, timeout=0.25):
			while not kill.isSet():
				try:
					yield qlist.get(timeout=timeout)
				except Queue.Empty:
					continue
		regen_threads = [threading.Thread(target=regen_iter, args=(iter_queue(kill, queue),)) for x in xrange(thread_count)]
		print "starting %d thread" % thread_count
		try:
			for x in regen_threads:
				x.start()
			print "started"
			# now we feed the queue.
			for pkg in repo:
				count += 1
				queue.put(pkg)
		except Exception:
			kill.set()
			reclaim_threads(regen_threads)
			raise			

		# by now, queue is fed.  reliable for our uses since the queue is only subtracted from.
		while not queue.empty():
			time.sleep(.5)
		kill.set()
		reclaim_threads(regen_threads)
		assert queue.empty()
	print "finished %d nodes in in %.2f seconds" % (count, time.time() - start_time)
