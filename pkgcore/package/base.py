# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
base package class; instances should derive from this.

Right now, doesn't provide much, need to change that down the line
"""

class base(object):
    
    _get_attr = {}
    
    def __setattr__(self, name, value):
        raise AttributeError(name)
    
    def __delattr__(self, attr):
        raise AttributeError(name)
    
    def __getattr__(self, attr):
        try:
            val = self.__dict__[attr] = self._get_attr[attr](self)
            return val
        except KeyError:
            raise AttributeError(attr)
    
    @property
    def versioned_atom(self):
        raise NotImplementedError(self, "versioned_atom")

    @property
    def unversioned_atom(self):
        raise NotImplementedError(self, "versioned_atom")
