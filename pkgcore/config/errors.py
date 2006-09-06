# Copyright: 2005 Marien Zwart <marienz@gentoo.org>
# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

# potentially use an intermediate base for user config errors,
# seperate base for instantiation?


"""Exceptions raised by the config code."""


class BaseException(Exception):
    pass


class TypeDefinitionError(BaseException):
    """Fatal error in type construction."""


class ConfigurationError(BaseException):
    """Fatal error in parsing a config section."""


class InstantiationError(BaseException):
    """Exception occured during instantiation.

    @ivar exc: Actual exception.
    """
    def __init__(self, callablename, pargs, kwargs, exception):
        BaseException.__init__(self, "Caught exception '%s' instantiating %s" %
                               (exception, callablename))
        self.callable = callablename
        self.pargs = pargs
        self.kwargs = kwargs
        self.exc = exception


class QuoteInterpretationError(BaseException):

    """Quoting of a var was screwed up.

    It may be useful to catch this and raise a ConfigurationError at a
    point where the filename is known.
    """

    def __init__(self, string):
        BaseException.__init__(self, "Parsing of %r failed" % (str,))
        self.str = string
