# Copyright: 2005 Brian Harring <ferringb@gmail.com>
# License: GPL2

# XXX yes; this location sucks, but we need some way to castrate the sandbox 
# if we're ever invoked w/in it.
import os
if os.environ.get("SANDBOX_ON", 0) and not \
    os.environ.get("PKGCORE_INTENTIONALLY_SANDBOXED", False):
    os.environ["SANDBOX_ON"] = '0'
