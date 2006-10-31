# Copyright: 2006 Marien Zwart <marienz@gentoo.org>
# License: GPL2


"""Classes implementing the descriptor protocol."""


class classproperty(object):

    """Like the builtin C{property} but takes a single classmethod.

    Used like this:

    class Example(object):

        @classproperty
        def test(cls):
            # Do stuff with cls here (it is Example or a subclass).

    Now both C{Example.test} and C{Example().test} invoke the getter.
    A "normal" property only works on instances.
    """

    def __init__(self, getter):
        self.getter = getter

    def __get__(self, instance, owner):
        return self.getter(owner)
