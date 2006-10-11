# Copyright: 2005-2006 Brian Harring <ferringb@gmail.com>
# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""Regenerate a repository cache."""


import threading
import Queue
import time

from pkgcore.util import commandline


class OptionParser(commandline.OptionParser):

    def __init__(self):
        commandline.OptionParser.__init__(
            self, description=__doc__, usage='%prog [options] repo [threads]')

    def check_values(self, values, args):
        values, args = commandline.OptionParser.check_values(
            self, values, args)
        if not args:
            self.error('Need a repository name.')
        if len(args) > 2:
            self.error('I do not know what to do with more than 2 arguments')
        values.repo_name = args[0]
        if len(args) == 2:
            try:
                values.thread_count = int(args[1])
            except ValueError:
                self.error('%r should be an integer' % (args[1],))
            if values.thread_count <= 0:
                self.error('thread count needs to be at least 1')
        else:
            values.thread_count = 1
        return values, ()


def regen_iter(iterable, err):
    for x in iterable:
        try:
            x.keywords
        except RuntimeError:
            raise
        except Exception, e:
            err.write("caught exception %s for %s\n" % (e, x))

def reclaim_threads(threads, err):
    for x in threads:
        try:
            x.join()
        except RuntimeError:
            raise
        except Exception, e:
            err.write("caught exception %s reclaiming thread\n" % (e,))


def main(config, options, out, err):
    try:
        repo = config.repo[options.repo_name]
    except KeyError:
        err.write('repo %r was not found!\n' % (repo_name,))
        err.write('known repos:\n%s\n' % (
                ', ',join(str(x) for x in conf.repo.iterkeys()),))
        return 1
    start_time = time.time()
    # HACK: store this here so we can assign to it from inside def passthru.
    options.count = 0
    if options.thread_count == 1:
        def passthru(iterable):
            for x in iterable:
                options.count += 1
                yield x
        regen_iter(passthru(repo), err)
    else:
        queue = Queue.Queue(options.thread_count * 2)
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
                target=regen_iter, args=(iter_queue(kill, queue), err))
            for x in xrange(options.thread_count)]
        out.write('starting %d threads' % (options.thread_count,))
        try:
            for x in regen_threads:
                x.start()
            out.write('started')
            # now we feed the queue.
            for pkg in repo:
                options.count += 1
                queue.put(pkg)
        except Exception:
            kill.set()
            reclaim_threads(regen_threads, err)
            raise

        # by now, queue is fed. reliable for our uses since the queue
        # is only subtracted from.
        while not queue.empty():
            time.sleep(.5)
        kill.set()
        reclaim_threads(regen_threads, err)
        assert queue.empty()
    out.write(
        "finished %d nodes in in %.2f seconds" % (
            options.count, time.time() - start_time))
    return 0
