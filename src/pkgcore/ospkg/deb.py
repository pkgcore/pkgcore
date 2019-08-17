import time

from snakeoil.data_source import text_data_source
from snakeoil.osutils import pjoin, unlink_if_exists
from snakeoil.process.spawn import spawn

from pkgcore.fs import tar, fs, contents

OPS = {
    '>=': (True, '>='),
    '!<': (False, '<<'),
}


def parsedeps(s):

    #pkgs = s #(' ')
    pkgs = s.split(' ')
    deps = []
    cons = []

    for pkg in pkgs:

        cat, name = pkg.split('/', 1)
        name = name.split('-', 1)
        if len(name) == 1:
            name, ver = name, None
        else:
            name, ver = name
        cstart = min(i for (i, c) in enumerate(cat) if c.isalpha())
        op, cat = cat[:cstart], cat[cstart:]

        if not op:
            deps.append((name, None, None))
            continue

        dop = OPS[op]
        if dop[0]:
            deps.append((name, dop[1], ver))
        else:
            cons.append((name, dop[1], ver))

    sdeps = []
    for name, op, ver in deps:
        if op is None or ver is None:
            assert op is None and ver is None
            sdeps.append(name)
            continue
        sdeps.append('%s (%s %s)' % (name, op, ver))

    scons = []
    for name, op, ver in cons:
        if op is None or ver is None:
            assert op is None and ver is None
            cons.append(name)
            continue
        scons.append('%s (%s %s)' % (name, op, ver))

    #return {'Depends': ', '.join(sdeps), 'Conflicts': ', '.join(scons)}
    ret = {'Depends': ', '.join(sdeps)}
    if scons and scons != "":
        ret['Conflicts'] = ', '.join(scons)
    return ret


def write(tempspace, finalpath, pkg, cset=None, platform='', maintainer='', compressor='gz'):

    # The debian-binary file

    if cset is None:
        cset = pkg.contents

    # The data.tar.gz file

    data_path = pjoin(tempspace, 'data.tar.gz')
    tar.write_set(cset, data_path, compressor='gz', absolute_paths=False)

    # Control data file

    control = {}
    control['Package'] = pkg.package
    #control['Section'] = pkg.category
    control['Version'] = pkg.fullver
    control['Architecture'] = platform
    if maintainer:
        control['Maintainer'] = maintainer
    control['Description'] = pkg.description
    pkgdeps = "%s" % (pkg.rdepend,)
    if (pkgdeps is not None and pkgdeps != ""):
        control.update(parsedeps(pkgdeps))

    control_ds = text_data_source("".join("%s: %s\n" % (k, v)
        for (k, v) in control.items()))

    control_path = pjoin(tempspace, 'control.tar.gz')
    tar.write_set(
        contents.contentsSet([
            fs.fsFile('control',
                {'size':len(control_ds.text_fileobj().getvalue())},
                data=control_ds,
                uid=0, gid=0, mode=0o644, mtime=time.time())
            ]),
        control_path, compressor='gz')
    dbinary_path = pjoin(tempspace, 'debian-binary')
    with open(dbinary_path, 'w') as f:
        f.write("2.0\n")
    ret = spawn(['ar', '-r', finalpath, dbinary_path, data_path, control_path])
    if ret != 0:
        unlink_if_exists(finalpath)
        raise Exception("failed creating archive: return code %s" % (ret,))
