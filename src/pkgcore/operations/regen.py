from snakeoil.compatibility import IGNORED_EXCEPTIONS

from ..package.errors import MetadataException
from ..util.thread_pool import map_async


def regen_iter(iterable, regen_func, observer):
    for pkg in iterable:
        try:
            regen_func(pkg)
        except IGNORED_EXCEPTIONS as e:
            if isinstance(e, KeyboardInterrupt):
                return
            raise
        except MetadataException:
            # handled at a higher level by scanning for metadata masked pkgs
            # after regen has completed
            pass
        except Exception as e:
            yield pkg, e


def regen_repository(repo, pkgs, observer, threads=1, pkg_attr='keywords', **kwargs):
    helpers = []

    def _get_repo_helper():
        if not hasattr(repo, '_regen_operation_helper'):
            return lambda pkg: getattr(pkg, 'keywords')
        # for an actual helper, track it and invoke .finish if it exists.
        helper = repo._regen_operation_helper(**kwargs)
        helpers.append(helper)
        return helper

    def get_args():
        return (_get_repo_helper(), observer)

    errors = map_async(pkgs, regen_iter, threads=threads, per_thread_args=get_args)

    # yield any errors that occurred during metadata generation
    yield from errors
