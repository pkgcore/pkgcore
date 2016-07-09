# cython: c_string_type=str, c_string_encoding=ascii
cimport _elib
from cpython.object cimport Py_LT, Py_LE, Py_EQ, Py_GT, Py_GE, Py_NE
from pkgcore.ebuild.errors import InvalidCPV

cdef class cpv(object):
    cdef _elib.CPV *_cpv

    cdef readonly str category
    cdef readonly str package
    cdef readonly str cpvstr
    cdef readonly str key
    cdef readonly str version
    cdef readonly str fullver
    cdef readonly object revision

    def __init__(self, *args, versioned=True):
        for x in args:
            if not isinstance(x, basestring):
                raise TypeError("all args must be strings, got %r" % (args,))
        cdef Py_ssize_t l = len(args)
        if l == 1:
            cpv_arg = args[0]
        elif l == 3:
            cpv_arg = "%s/%s-%s" % args
        else:
            raise TypeError("CPV takes 1 arg (cpvstr), or 3 (cat, pkg, ver):"
                " got %r" % (args,))

        self._cpv = _elib.cpv_alloc(cpv_arg, versioned)
        if self._cpv is NULL:
            raise InvalidCPV(_elib.ebuild_strerror(_elib.ebuild_errno))
        self.category = self._cpv.CATEGORY
        self.package = self._cpv.PN
        self.key = self.category + "/" + self.package
        if versioned:
            self.cpvstr = self.key + "-" + self._cpv.PVR
            self.version = self._cpv.PV
            self.fullver = self._cpv.PVR
            self.revision = self._cpv.PR_int if self._cpv.PR_int else None
        else:
            self.cpvstr = self.key
            self.version = None 
            self.fullver = None
            self.revision = None

    def __dealloc__(self):
        _elib.cpv_free(self._cpv)

    def __str__(self):
        return self.cpvstr 

    def __repr__(self):
        return '<%s %s @#%x>' % (
            self.__class__.__name__, self.cpvstr, id(self))

    def __hash__(self):
        return hash(self.cpvstr)
    
    def __richcmp__(cpv self, cpv other, int op):
        cdef _elib.cmp_code ret = _elib.cpv_cmp(self._cpv, other._cpv)
        if   op == Py_LT:
            return ret == _elib.OLDER
        elif op == Py_LE:
            return ret == _elib.OLDER or ret == _elib.EQUAL
        elif op == Py_EQ:
            return ret == _elib.EQUAL
        elif op == Py_NE:
            return ret != _elib.EQUAL
        elif op == Py_GT:
            return ret == _elib.NEWER
        elif op == Py_GE:
            return ret == _elib.NEWER or ret == _elib.EQUAL
        else:
            assert False
