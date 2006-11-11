# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

"""
instance caching metaclass
"""
from pkgcore.util.demandload import demandload
demandload(globals(), "warnings weakref:WeakValueDictionary")

class native_WeakInstMeta(type):
    """"metaclass for instance caching, resulting in reuse of unique instances

    few notes-
      - instances must be immutable (or effectively so).
        Since creating a new instance may return a preexisting instance,
        this requirement B{must} be honored.
      - due to the potential for mishap, each subclass of a caching class must
        assign __inst_caching__ = True to enable caching for the derivative.
      - conversely, __inst_caching__ = False does nothing
        (although it's useful as a sign of
        I{do not enable caching for this class}
      - instance caching can be disabled per instantiation via passing
        disabling_inst_caching=True into the class constructor.

    Being a metaclass, the voodoo used doesn't require modification of
    the class itself.

    Examples of usage are the restriction modules
    L{packages<pkgcore.restrictions.packages>} and
    L{values<pkgcore.restrictions.values>}
    """
    def __new__(cls, name, bases, d):
        if d.get("__inst_caching__", False):
            d["__inst_caching__"] = True
            d["__inst_dict__"]  = WeakValueDictionary()
        else:
            d["__inst_caching__"] = False
        slots = d.get('__slots__')
        if slots is not None:
            for base in bases:
                if getattr(base, '__weakref__', False):
                    break
            else:
                d['__slots__'] = tuple(slots) + ('__weakref__',)
        return type.__new__(cls, name, bases, d)

    def __call__(cls, *a, **kw):
        """disable caching via disable_inst_caching=True"""
        if cls.__inst_caching__ and not kw.pop("disable_inst_caching", False):
            kwlist = kw.items()
            kwlist.sort()
            key = (a, tuple(kwlist))
            try:
                instance = cls.__inst_dict__.get(key)
            except (NotImplementedError, TypeError), t:
                warnings.warn(
                    "caching keys for %s, got %s for a=%s, kw=%s" % (
                        cls, t, a, kw))
                del t
                key = instance = None

            if instance is None:
                instance = super(native_WeakInstMeta, cls).__call__(*a, **kw)

                if key is not None:
                    cls.__inst_dict__[key] = instance
        else:
            instance = super(native_WeakInstMeta, cls).__call__(*a, **kw)

        return instance

# "Invalid name"
# pylint: disable-msg=C0103

try:
    # No name in module
    # pylint: disable-msg=E0611
    from pkgcore.util._caching import WeakInstMeta
    cpy_WeakInstMeta = WeakInstMeta
except ImportError:
    cpy_WeakInstMeta = None
    WeakInstMeta = native_WeakInstMeta
