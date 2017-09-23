# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
misc. repository related tools
"""

__all__ = ("get_raw_repos", "get_virtual_repos")

# TODO: deprecated, drop support in 0.10
from pkgcore.repository.util import get_raw_repos, get_virtual_repos
