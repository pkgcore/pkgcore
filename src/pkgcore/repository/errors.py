# Copyright: 2005-2008 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

"""
exceptions thrown by repository classes.

Need to extend the usage a bit further still.
"""

__all__ = ("TreeCorruption", "InitializationError")


class TreeCorruption(Exception):

    def __init__(self, err):
        super().__init__(f'unexpected tree corruption: {err}')
        self.err = err


class InitializationError(TreeCorruption):

    def __str__(self):
        return f"repo init failed: {self.err}"
