#!/usr/bin/env python3

from pkgcore.config import load_config
from pkgcore.util.file_type import file_identifier

debug_paths = ["/usr/lib/debug"]

fi = file_identifier()
vdbs = load_config().get_default("domain").all_installed_repos
for pkg in sorted(vdbs):
    contents = getattr(pkg, 'contents', ())
    if not contents:
        continue
    files = contents.iterfiles()

    for obj in files:
        res = fi(obj.location)
        if res is None:
            # nonexistent file.
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
        print(f"{pkg.key}:{pkg.slot}")
