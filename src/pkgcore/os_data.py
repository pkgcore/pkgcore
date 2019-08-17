"""
Avoid using- os data- root uid/gid, pkgcore uid/gid, etc.

This will be killed off and bound into configuration subsystem at some point
"""

__all__ = (
    "ostype", "portage_gid", "portage_uid", "root_gid", "root_uid",
    "userland", "wheelgid", "xargs",
)

import grp
import os
import pwd

ostype = os.uname()[0]

if ostype in ("Linux", "CYGWIN_NT-5.1"):
    userland = "GNU"
    xargs = os.environ["XARGS"] = "xargs -r"
    lchown = os.lchown
elif ostype == "Darwin":
    userland = "Darwin"
    xargs = os.environ["XARGS"] = "xargs"

    def lchown(*pos_args, **key_args):
        pass

elif ostype in ("FreeBSD", "OpenBSD", "NetBSD", "SunOS"):
    userland = "BSD"
    xargs = os.environ["XARGS"] = "xargs"
    lchown = os.lchown
else:
    raise Exception("Operating system unsupported, '%s'" % ostype)

uid = os.getuid()
gid = os.getgid()
# hard coding sucks.
root_uid = 0
root_gid = wheelgid = 0

try:
    wheelgid = grp.getgrnam("wheel").gr_gid
except KeyError:
    pass

# Discover the uid and gid of the portage user/group
try:
    portage_uid = pwd.getpwnam("portage").pw_uid
    portage_gid = grp.getgrnam("portage").gr_gid
    portage_user_groups = tuple(x.gr_name for x in grp.getgrall()
                                if 'portage' in x.gr_mem)
except KeyError:
    portage_uid = 0
    portage_gid = wheelgid
    portage_user_groups = []
