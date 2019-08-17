"""
WARNING: this module is for testing usage only; it disables
the default strictness tests that fsBase.* derivatives have to ease
testing.  Do not use it in non-test code.
"""

# we use pre_curry to preserve the docs for the wrapped target
from snakeoil.currying import pre_curry

from pkgcore.fs import fs

# we're anal about del'ing here to prevent the vars from lingering around,
# showing up when folks are poking around

key = None
for key in dir(fs):
    val = getattr(fs, key)
    # protection; issubclass pukes if it's not a class.
    # downside, this works on new style only
    if isinstance(val, type) and issubclass(val, fs.fsBase) and \
            val is not fs.fsBase:
        locals()[f"_original_{key}"] = val
        val = pre_curry(val, strict=False)
        val.__doc__ = locals()[f"_original_{key}"].__doc__
    locals()[key] = val
    del val

del key
