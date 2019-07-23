# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD 3 clause

from snakeoil.compatibility import IGNORED_EXCEPTIONS

from pkgcore.package.errors import MetadataException
from pkgcore.restrictions import packages
from pkgcore.util.thread_pool import map_async


def regen_iter(iterable, regen_func, observer, is_thread=False):
    for pkg in iterable:
        try:
            regen_func(pkg)
        except IGNORED_EXCEPTIONS as e:
            if isinstance(e, KeyboardInterrupt):
                return
            raise
        except MetadataException as e:
            observer.error(f'{pkg.cpvstr}: {e.msg(verbosity=observer.verbosity)}')
        except Exception as e:
            observer.error(f'caught exception {e} while processing {pkg.cpvstr}')


def regen_repository(repo, observer, threads=1, pkg_attr='keywords', **kwargs):
    helpers = []

    def _get_repo_helper():
        if not hasattr(repo, '_regen_operation_helper'):
            return lambda pkg: getattr(pkg, 'keywords')
        # for an actual helper, track it and invoke .finish if it exists.
        helper = repo._regen_operation_helper(**kwargs)
        helpers.append(helper)
        return helper

    # force usage of unfiltered repo to include pkgs with metadata issues
    pkgs = repo.itermatch(packages.AlwaysTrue, pkg_filter=None)
    if threads == 1:
        regen_iter(pkgs, _get_repo_helper(), observer)
    else:
        def get_args():
            return (_get_repo_helper(), observer, True)
        map_async(pkgs, regen_iter, per_thread_args=get_args)

    for helper in helpers:
        f = getattr(helper, 'finish', None)
        if f is not None:
            f()
