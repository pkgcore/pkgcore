"""This is internal, do not use it externally, nor add any further usage of it.

This is a version of tarfile modified strictly for snakeoil.data_sources usage.

This is will be removed once pkgcore and snakeoil data_source usage is removed.
"""

from snakeoil.python_namespaces import protect_imports


# force a fresh module import of tarfile that is ours to monkey patch.
with protect_imports() as (_paths, modules):
    modules.pop("tarfile", None)
    tarfile = __import__("tarfile")


# add in a tweaked ExFileObject that is usable by snakeoil.data_source
class ExFileObject(tarfile.ExFileObject):
    __slots__ = ()
    exceptions = (EnvironmentError,)


tarfile.fileobject = ExFileObject

# finished monkey patching. now to lift things out of our tarfile
# module into this scope so from/import behaves properly.

locals().update((k, getattr(tarfile, k)) for k in tarfile.__all__)
