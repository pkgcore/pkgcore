# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

# stuck here to break the nasty _cpv cpv cycle- use cpv instead.
from pkgcore.package import errors

class InvalidCPV(errors.InvalidPackage):
    """Raised if an invalid cpv was passed in.

    @ivar args: single-element tuple containing the invalid string.
    @type args: C{tuple}
    """

