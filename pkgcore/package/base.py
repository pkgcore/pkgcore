# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
base package class; instances should derive from this.

Right now, doesn't provide much, need to change that down the line
"""

class base(object):

    __slots__ = ("__weakref__", )
    _get_attr = {}

    def __setattr__(self, attr, value):
        raise AttributeError(attr)

    def __delattr__(self, attr):
        raise AttributeError(attr)

    def __getattr__(self, attr):
        try:
            val = self._get_attr[attr](self)
            object.__setattr__(self, attr, val)
            return val
        except KeyError:
            raise AttributeError(attr)

    @property
    def versioned_atom(self):
        raise NotImplementedError(self, "versioned_atom")

    @property
    def unversioned_atom(self):
        raise NotImplementedError(self, "versioned_atom")
