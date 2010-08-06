# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

# "More than one statement on a single line"
# pylint: disable-msg=C0321

"""
atom exceptions
"""

__all__ = ("MalformedAtom", "InvalidVersion", "InvalidCPV", "ParseError")

from pkgcore.package import errors

class MalformedAtom(errors.InvalidDependency):

    def __init__(self, atom, err=''):
        errors.InvalidDependency.__init__(
            self, "atom '%s' is malformed: error %s" % (atom, err))
        self.atom, self.err = atom, err


class InvalidVersion(errors.InvalidDependency):

    def __init__(self, ver, rev, err=''):
        errors.InvalidDependency.__init__(
            self,
            "Version restriction ver='%s', rev='%s', is malformed: error %s" %
            (ver, rev, err))
        self.ver, self.rev, self.err = ver, rev, err


class InvalidCPV(errors.InvalidPackageName):
    """Raised if an invalid cpv was passed in.

    @ivar args: single-element tuple containing the invalid string.
    :type args: C{tuple}
    """


class ParseError(errors.InvalidDependency):

    def __init__(self, s, token=None, msg=None):
        if msg is None:
            str_msg = ''
        else:
            str_msg = ': %s' % msg
        if token is not None:
            Exception.__init__(self,
                "%s is unparseable%s\nflagged token- %s" %
                               (s, str_msg, token))
        else:
            Exception.__init__(self,
                "%s is unparseable%s" % (s, str_msg))
        self.dep_str, self.token, self.msg = s, token, msg
