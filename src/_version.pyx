# cython: c_string_type=str, c_string_encoding=ascii
cimport _elib
from pkgcore.ebuild.errors import InvalidVersion

def version_cmp(v1, v2):
    cdef _elib.cmp_code ret = _elib.version_cmp(v1, v2)
    if ret == _elib.ERROR:
        raise InvalidVersion(v1, v2)
    return ret

def version_cmp_ext(v1, r1, v2, r2):
    if v1 == None:
        if v2 == None:
            return 0
        else:
            return -1
    elif v2 == None:
        return 1

    if r1 != None:
        v1 = v1 + "-r" + str(r1)
    if r2 != None:
        v2 = v2 + "-r" + str(r2)

    return version_cmp(v1, v2)

def version_match(v1, v2, operation):
    cdef _elib.atom_op op = _elib.atom_op_from_str(operation)
    cdef int ret = _elib.version_match(v1, v2, op)
    if ret == -1:
        raise InvalidVersion(v1, v2)
    return ret > 0
