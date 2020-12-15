# potentially use an intermediate base for user config errors,
# separate base for instantiation?

"""Exceptions raised by the config code."""

__all__ = (
    "TypeDefinitionError", "ConfigurationError", "ParsingError",
    "CollapseInheritOnly", "ComplexInstantiationError",
    "QuoteInterpretationError",
)

from ..exceptions import PkgcoreException, PkgcoreUserException


def _identify_functor_source(functor):
    module = getattr(functor, '__module__', None)
    if module is None:
        return functor.__name__
    return f'{module}.{functor.__name__}'


class ConfigError(PkgcoreException):
    """Generic config exception."""


class UserConfigError(ConfigError, PkgcoreUserException):
    """Generic config exception with user relevant error."""


class TypeDefinitionError(ConfigError):
    """Fatal error in type construction."""


class ConfigurationError(ConfigError):
    """Fatal error in parsing a config section.

    :type stack: sequence of strings.
    :ivar stack: messages describing where this ConfigurationError originated.
        configuration-related code catching ConfigurationError that wants to
        raise its own ConfigurationError should modify (usually append to)
        the stack and then re-raise the original exception (this makes sure
        the traceback is preserved).
    """

    def __init__(self, message):
        super().__init__(message)
        self.stack = [message]

    def __str__(self):
        return ':\n'.join(reversed(self.stack))


class ParsingError(ConfigurationError, PkgcoreUserException):
    """Generic file parsing exception."""

    def __init__(self, message=None, exception=None):
        if message is not None:
            super().__init__(message)
        elif exception is not None:
            super().__init__(str(exception))
        else:
            raise ValueError('specify at least one of message and exception')
        self.message = message
        self.exc = exception

    def __str__(self):
        msg = f'parsing failed: {self.message}'
        if self.exc is not None:
            msg += f'\n{self.exc}'
        return msg


class CollapseInheritOnly(ConfigurationError):
    """Attempt was made to collapse an uncollapsable section.

    Separate exception because pconfig catches it separately.
    """


class InstantiationError(ConfigurationError):

    _txt = "Failed instantiating section %r%s"

    def __init__(self, section_name, message=None):
        self.section_name = section_name
        self.message = message

    def __str__(self):
        s = self.message
        if s is None:
            s = ''
        else:
            s = ': %s' % (s,)
        return self._txt % (self.section_name, s)


class AutoloadInstantiationError(InstantiationError):

    _txt = "Failed loading autoload section %r%s"


class ComplexInstantiationError(ConfigurationError):
    """Exception occurred during instantiation.

    :ivar callable: callable object which failed during instantiation.
    :ivar pargs: positional args passed to callable.
    :ivar kwargs: keyword args passed to callable.
    :ivar exc: original exception object or None.

    A well-behaved configurable callable should raise this exception
    if instantiation failed, providing one or both of message and
    exception. The other fields will be filled in by central.

    If the callable raises something else central will wrap it in
    this, but that will lose the traceback.
    """

    def __init__(self, message=None, exception=None, callable_obj=None,
                 pargs=None, kwargs=None):
        if message is not None:
            super().__init__(message)
        elif exception is not None:
            super().__init__(str(exception))
        else:
            raise ValueError('specify at least one of message and exception')
        self.message = message
        self.callable = callable_obj
        self.pargs = pargs
        self.kwargs = kwargs
        self.exc = exception

    def __str__(self):
        # self.callable should be set here (nothing should try to catch
        # and str() this before central had a chance to fill it in)
        if self.message is not None:
            if self.callable is None:
                message = f'{self.message!r}, callable unset!'
            else:
                message = (
                    f'{self.message!r} instantiating '
                    f'{self.callable.__module__}.{self.callable.__name__}'
                )
        # The weird repr(str(exc)) used here quotes the message nicely.
        elif self.callable is not None:
            message = (
                f'Caught exception {str(self.exc)!r} '
                f'instantiating {self.callable.__module__}.{self.callable.__name__}'
            )
        else:
            message = f'Caught exception {str(self.exc)!r}, callable unset!'
        return ':\n'.join(reversed([message] + self.stack[1:]))


class QuoteInterpretationError(ConfigurationError):
    """Quoting of a var was screwed up."""

    def __init__(self, string):
        super().__init__(f'parsing of {string!r} failed')
        self.str = string
