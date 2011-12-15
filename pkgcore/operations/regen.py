# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD 3 clause

import time
import Queue
import threading
import thread

from snakeoil import compatibility

def regen_iter(iterable, observer, regen_func, is_thread=False):
    for x in iterable:
        try:
            regen_func(x)
        except compatibility.IGNORED_EXCEPTIONS, e:
            if isinstance(e, KeyboardInterrupt):
                return
            raise
        except Exception, e:
            observer.error("caught exception %s while processing %s" % (e, x))

def reclaim_threads(threads, observer):
    for x in threads:
        try:
            x.join()
        except compatibility.IGNORED_EXCEPTIONS:
            raise
        except Exception, e:
            observer.error("caught exception %s reclaiming thread" % (e,))


def regen_repository(repo, observer, threads=1, pkg_attr='keywords', **options):

    helpers = []
    def _get_repo_helper():
        if not hasattr(repo, '_regen_operation_helper'):
            return lambda pkg:getattr(pkg, 'keywords')
        # for an actual helper, track it and invoke .finish if it exists.
        helper = repo._regen_operation_helper(**options)
        helpers.append(helper)
        return helper

    if threads == 1:
        def passthru(iterable):
            global count
            for x in iterable:
                yield x
        regen_iter(passthru(repo), observer, _get_repo_helper())
    else:
        # note we allow an infinite queue since .put below
        # is blocking, and won't return till it succeeds (regardless of signal)
        # as such, we do it this way to ensure the put succeeds, then the keyboardinterrupt
        # can be seen.
        queue = Queue.Queue()
        kill = threading.Event()
        kill.clear()
        def iter_queue(kill, qlist, timeout=0.5):
            while not kill.isSet():
                try:
                    yield qlist.get(timeout=timeout)
                except Queue.Empty:
                    continue
        regen_threads = [
            threading.Thread(
                target=regen_iter, args=(iter_queue(kill, queue), observer,
                    _get_repo_helper(), True))
            for x in xrange(threads)]
        try:
            failed = True
            for x in regen_threads:
                x.start()
            # now we feed the queue.
            for pkg in repo:
                queue.put(pkg)
            failed = False
        finally:
            if not failed:
                while not queue.empty():
                    time.sleep(0.5)

            kill.set()
            reclaim_threads(regen_threads, observer)

        assert queue.empty()

    for helper in helpers:
        f = getattr(helper, 'finish', None)
        if f is not None:
            f()
