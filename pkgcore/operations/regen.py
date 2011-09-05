# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD 3 clause

import time
import Queue
import threading
import itertools

from snakeoil import compatibility

def regen_iter(iterable, observer, attribute):
    for x in iterable:
        try:
            getattr(x, attribute)
        except compatibility.IGNORED_EXCEPTIONS:
            raise
        except Exception, e:
            observer.error("caught exception %s for %s" % (e, x))

def reclaim_threads(threads, observer):
    for x in threads:
        try:
            x.join()
        except compatibility.IGNORED_EXCEPTIONS:
            raise
        except Exception, e:
            observer.error("caught exception %s reclaiming thread" % (e,))

def regen_repository(repo, observer, threads=1, pkg_attr='keywords'):
    # HACK: store this here so we can assign to it from inside def passthru.
#    if not options.disable_eclass_preloading:
#        processor._global_enable_eclass_preloading = True
    if threads == 1:
        def passthru(iterable):
            global count
            for x in iterable:
                yield x
        regen_iter(passthru(repo), observer, pkg_attr)
    else:
        queue = Queue.Queue(threads * 2)
        kill = threading.Event()
        kill.clear()
        def iter_queue(kill, qlist, timeout=0.25):
            while not kill.isSet():
                try:
                    yield qlist.get(timeout=timeout)
                except Queue.Empty:
                    continue
        regen_threads = [
            threading.Thread(
                target=regen_iter, args=(iter_queue(kill, queue), observer,
                    pkg_attr))
            for x in xrange(threads)]
        try:
            for x in regen_threads:
                x.start()
            # now we feed the queue.
            for pkg in repo:
                queue.put(pkg)
        except Exception:
            kill.set()
            reclaim_threads(regen_threads, observer)
            raise

        # by now, queue is fed. reliable for our uses since the queue
        # is only subtracted from.
        while not queue.empty():
            time.sleep(.5)
        kill.set()
        reclaim_threads(regen_threads, observer)
        assert queue.empty()
