# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD 3 clause

import threading
import Queue
import time
from snakeoil.demandload import demandload
demandload(globals(),
    'snakeoil.process:get_proc_count',
)

def reclaim_threads(threads):
    for x in threads:
        try:
            x.join()
        except compatibility.IGNORED_EXCEPTIONS:
            raise
        except Exception, e:
            # should do something better here
            pass

def map_async(iterable, functor, *args, **kwds):
    per_thread_args = kwds.pop("per_thread_args", lambda:())
    per_thread_kwds = kwds.pop("per_thread_kwds", lambda:{})
    parallelism = kwds.pop("threads", None)
    if parallelism is None:
        parallelism = get_proc_count()

    if hasattr(iterable, '__len__'):
        # if there are less items than parallelism, don't
        # spawn pointless threads.
        paralleism = max(min(len(iterable), parallelism), 0)

    # note we allow an infinite queue since .put below
    # is blocking, and won't return till it succeeds (regardless of signal)
    # as such, we do it this way to ensure the put succeeds, then the keyboardinterrupt
    # can be seen.
    queue = Queue.Queue()
    kill = threading.Event()
    kill.clear()
    def iter_queue(kill, qlist, empty_signal):
        while not kill.isSet():
            item = qlist.get()
            if item is empty_signal:
                return
            yield item

    empty_signal = object()

    threads = []
    for x in xrange(parallelism):
        tkwds = kwds.copy()
        tkwds.update(per_thread_kwds())
        targs = (iter_queue(kill, queue, empty_signal),) + args + per_thread_args()
        threads.append(threading.Thread(target=functor, args=targs, kwargs=tkwds))
    try:
        try:
            failed = True
            for x in threads:
                x.start()
            # now we feed the queue.
            for data in iterable:
                queue.put(data)
        except:
            kill.set()
            raise
    finally:
        for x in xrange(parallelism):
            queue.put(empty_signal)

        reclaim_threads(threads)

    assert queue.empty()
