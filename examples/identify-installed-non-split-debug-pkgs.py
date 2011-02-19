#!/usr/bin/python
from pkgcore.config import load_config
from pkgcore.util.file_type import file_identifier
from snakeoil.compatibility import any

import re
debug_paths = ["/usr/lib%s/debug" % (x,) for x in ("64", "32", "")]

fi = file_identifier()
vdbs = load_config().get_default("domain").vdb
for repo in vdbs:
    for pkg in repo:
        contents = getattr(pkg, 'contents', ())
        if not contents:
            continue
        files = contents.iterfiles()

        for obj in files:
            res = fi(obj.location)
            if res is None:
                # nonexistant file.
                continue
            if res.startswith("ELF "):
                break
        else:
            # no elf objects
            continue

        for path in debug_paths:
            if path in contents:
                break
        else:
            # no debug bits, but is elf.
            print "%s:%s" % (pkg.key, pkg.slot)
