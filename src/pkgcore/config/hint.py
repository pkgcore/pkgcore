"""Config introspection support."""

__all__ = ("ConfigHint", "configurable")

import typing


class ConfigHint:
    """Hint for introspection supplying overrides."""

    types: dict[str, str]
    positional: tuple[str, ...]
    required: tuple[str, ...]
    typename: str | None
    allow_unknowns: bool
    authorative: bool
    requires_config: bool
    raw_class: bool

    # be aware this is used in clone
    __slots__ = (
        "allow_unknowns",
        "authorative",
        "doc",
        "positional",
        "raw_class",
        "required",
        "requires_config",
        "typename",
        "types",
    )

    def __init__(
        self,
        types: dict[str, str] | None = None,
        positional: typing.Sequence[str] | None = None,
        required: typing.Sequence[str] | None = None,
        doc: str | None = None,
        typename: str | None = None,
        allow_unknowns: bool = False,
        authorative: bool = False,
        requires_config: bool = False,
        raw_class: bool = False,
    ) -> None:
        self.types = types or {}
        self.positional = tuple(positional or [])
        self.required = tuple(required or [])
        self.typename = typename
        self.allow_unknowns = allow_unknowns
        self.doc = doc
        self.authorative = authorative
        self.requires_config = requires_config
        self.raw_class = raw_class

    def clone(self, **kwds: typing.Any) -> "ConfigHint":
        """return a copy of this ConfigHint with the given kwds overrides"""
        new_kwds = {}
        for attr in self.__slots__:
            new_kwds[attr] = kwds.pop(attr, getattr(self, attr))
        if kwds:
            raise TypeError(f"unknown type overrides: {kwds!r}")
        return self.__class__(**new_kwds)


def configurable(**kwargs):
    """Decorator version of ConfigHint."""
    hint = ConfigHint(**kwargs)

    def decorator(original):
        original.pkgcore_config_type = hint
        return original

    return decorator
