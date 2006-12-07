/*
 * Copyright: 2006 Brian Harring <ferringb@gmail.com>
 * License: GPL2
 *
 * C version of some of pkgcore (for extra speed).
 */

/* This does not really do anything since we do not use the "#"
 * specifier in a PyArg_Parse or similar call, but hey, not using it
 * means we are Py_ssize_t-clean too!
 */

#define PY_SSIZE_T_CLEAN

#include <Python.h>
#include "py24-compatibility.h"
#include <sys/mman.h>
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>

// only 2.5.46 kernels and up have this.
#ifndef MAP_POPULATE
#define MAP_POPULATE 0
#endif

#define SKIP_SLASHES(ptr) while('/' == *(ptr)) (ptr)++;

static PyObject *
pkgcore_normpath(PyObject *self, PyObject *old_path)
{
    if(!PyString_CheckExact(old_path)) {
        PyErr_SetString(PyExc_TypeError,
            "old_path must be a str");
        return (PyObject *)NULL;
    }
    Py_ssize_t len = PyString_Size(old_path);
    if(!len)
        return PyString_FromString(".");
    
    char *oldstart, *oldp, *newstart, *newp, *real_newstart;
    oldstart = oldp = PyString_AsString(old_path);
    
    PyObject *new_path = PyString_FromStringAndSize(NULL, len);
    if(!new_path)
        return new_path;
    real_newstart = newstart = newp = PyString_AsString(new_path);
    

    int leading_slash;
    Py_ssize_t slash_count = 0;
    // /../ == / , ../foo == ../foo , ../foo/../../ == ../../../
    if('/' == *oldp) {
        *newp = '/';
        newp++;
        leading_slash = 1;
        slash_count++;
        SKIP_SLASHES(oldp);
        newstart = newp;
    } else {
        leading_slash = 0;
    }

    while('\0' != *oldp) {
        if('/' == *oldp) {
            *newp = '/';
            newp++;
            slash_count++;
            SKIP_SLASHES(oldp);
        }
        if('.' == *oldp) {
            oldp++;
            if('\0' == *oldp)
                break;
            if('/' == *oldp) {
                oldp++;
                SKIP_SLASHES(oldp);
                continue;
            }
            if(*oldp == '.' && ('/' == oldp[1] || '\0' ==  oldp[1])) {
                // for newp, ../ == ../ , /../ == /
                if(leading_slash == slash_count) {
                    if(!leading_slash) {
                        // ../ case.
                        newp[0] = '.';
                        newp[1] = '.';
                        newp[2] = '/';
                        newp += 3;
                    }
                } else if (slash_count != 1 || '/' != *newstart) {
                    // if its /, then the stripping would be ignored.
                    newp--;
                    while(newp > newstart && '/' != newp[-1])
                        newp--;
                }
                oldp++;
                SKIP_SLASHES(oldp);
                continue;
            }
            // funky file name.
            oldp--;
        }
        while('/' != *oldp && '\0' != *oldp) {
            *newp = *oldp;
            ++newp;
            ++oldp;
        }
    }

    *newp = '\0';
    // protect leading slash, but strip trailing.
    --newp;
    while(newp > real_newstart && '/' == *newp)
        newp--;

    // resize it now.
    _PyString_Resize(&new_path, newp - real_newstart + 1);
    return new_path;
}

static PyObject *
pkgcore_join(PyObject *self, PyObject *args)
{
    if(!args) {
        PyErr_SetString(PyExc_TypeError, "requires at least one path");
        return (PyObject *)NULL;
    }
    PyObject *fast = PySequence_Fast(args, "arg must be a sequence");
    if(!fast)
        return (PyObject *)NULL;
    Py_ssize_t end = PySequence_Fast_GET_SIZE(fast);
    if(!end) {
        PyErr_SetString(PyExc_TypeError,
            "join takes at least one arguement (0 given)");
        return (PyObject *)NULL;
    }
    
    PyObject **items = PySequence_Fast_ITEMS(fast);
    Py_ssize_t start = 0, len, i = 0;
    char *s;

    // find the right most item with a prefixed '/', else 0.
    for(; i < end; i++) {
        if(!PyString_CheckExact(items[i])) {
            PyErr_SetString(PyExc_TypeError, "all args must be strings");
            Py_DECREF(fast);
            return (PyObject *)NULL;
        }
        s = PyString_AsString(items[i]);
        if('/' == *s)
            start = i;
    }
    // know the relevant slice now; figure out the size.
    len = 0;
    char *s_start;
    for(i = start; i < end; i++) {
        // this is safe because we're using CheckExact above.
        s_start = s = PyString_AS_STRING(items[i]);
        while('\0' != *s)
            s++;
        len += s - s_start;
        s_start++;
        char *s_end = s;
        if(i + 1 != end) {
            while(s != s_start && '/' == s[-1])
                s--;
            if(s_end == s && (s_start != s ||
                (s_end == s_start && i != start))) {
                len++;
            } else if(s_start != s) {
                len -= s_end - s -1;
            }
        }
    }

    // ok... we know the length.  allocate a string, and copy it.
    PyObject *ret = PyString_FromStringAndSize(NULL, len);
    if(!ret)
        return (PyObject*)NULL;
    char *buf = PyString_AS_STRING(ret);
    for(i = start; i < end; i++) {
        s_start = s = PyString_AS_STRING(items[i]);
        while('\0' != *s) {
            *buf = *s;
            buf++;
            if('/' == *s) {
                char *tmp_s = s + 1;
                SKIP_SLASHES(s);
                if('\0' == *s) {
                    if(i + 1  != end) {
                        buf--;
                    } else {
                        // copy the cracked out trailing slashes on the
                        // last item
                        while(tmp_s < s) {
                            *buf = '/';
                            buf++;
                            tmp_s++;
                        }
                    }
                    break;
                } else {
                    // copy the cracked out intermediate slashes.
                    while(tmp_s < s) {
                        *buf = '/';
                        buf++;
                        tmp_s++;
                    }
                }
            } else
                s++;
        }
        if(i + 1 != end) {
            *buf = '/';
            buf++;
        }
    }
    *buf = '\0';
    Py_DECREF(fast);
    return ret;
}

// returns 0 on success opening, 1 on ENOENT but ignore, and -1 on failure
// if failure condition, appropriate exception is set.

static inline int
pkgcore_open_and_stat(PyObject *path,
    int *fd, Py_ssize_t *size)
{
    struct stat st;
    errno = 0;
    if((*fd = open(PyString_AsString(path), O_LARGEFILE)) >= 0) {
        int ret = fstat(*fd, &st);
        if(!ret) {
            *size = st.st_size;
            return 0;
        }
    }
    return 1;
}

static inline int
handle_failed_open_stat(int fd, Py_ssize_t size, PyObject *path,
PyObject *swallow_missing)
{
    if(fd < 0) {
        if(errno == ENOENT) {
            if(swallow_missing) {
                if(PyObject_IsTrue(swallow_missing)) {
                    errno = 0;
                    return 0;
                }
                if(PyErr_Occurred())
                    return 1;
            }
        }
        PyErr_SetFromErrnoWithFilenameObject(PyExc_IOError, path);
        return 1;
    }
    PyErr_SetFromErrnoWithFilenameObject(PyExc_OSError, path);
    if(close(fd))
        PyErr_SetFromErrnoWithFilenameObject(PyExc_IOError, path);
    return 1;
}

static PyObject *
pkgcore_readfile(PyObject *self, PyObject *args)
{
    PyObject *path, *swallow_missing = NULL;
    if(!args || !PyArg_ParseTuple(args, "S|O:readfile", &path,
        &swallow_missing)) {
        return (PyObject *)NULL;
    }
    Py_ssize_t size;
    int fd;
    Py_BEGIN_ALLOW_THREADS
    if(pkgcore_open_and_stat(path, &fd, &size)) {
        Py_BLOCK_THREADS
        if(handle_failed_open_stat(fd, size, path, swallow_missing))
            return NULL;
        Py_RETURN_NONE;
    }
    Py_END_ALLOW_THREADS

    int ret = 0;
    PyObject *data = PyString_FromStringAndSize(NULL, size);

    Py_BEGIN_ALLOW_THREADS
    errno = 0;
    if(data) {
        ret = size != read(fd, PyString_AS_STRING(data), size) ? 1 : 0;
    }
    ret += close(fd);
    Py_END_ALLOW_THREADS

    if(ret) {
        Py_CLEAR(data);
        data = PyErr_SetFromErrnoWithFilenameObject(PyExc_OSError, path);
    }
    return data;
}

typedef struct {
    PyObject_HEAD
    char *start;
    char *end;
    char *map;
    int fd;
    int strip_newlines;
    PyObject *fallback;
} pkgcore_readlines;


static PyObject *
pkgcore_readlines_new(PyTypeObject *type, PyObject *args, PyObject *kwargs)
{
    PyObject *path, *swallow_missing = NULL, *strip_newlines = NULL;
    PyObject *none_on_missing = NULL;
    pkgcore_readlines *self = NULL;
    if(kwargs && PyDict_Size(kwargs)) {
        PyErr_SetString(PyExc_TypeError,
            "readlines.__new__ doesn't accept keywords");
        return (PyObject *)NULL;
    } else if (!PyArg_ParseTuple(args, "S|OOO:readlines.__new__", 
        &path, &strip_newlines, &swallow_missing, &none_on_missing)) {
        return (PyObject *)NULL;
    } 
    
    int fd;
    Py_ssize_t size;
    void *ptr;
    PyObject *fallback = NULL;
    Py_BEGIN_ALLOW_THREADS
    errno = 0;
    if(pkgcore_open_and_stat(path, &fd, &size)) {
        Py_BLOCK_THREADS

        if(handle_failed_open_stat(fd, size, path, swallow_missing))
            return NULL;

        // return an empty tuple, and let them iter over that.
        if(none_on_missing && PyObject_IsTrue(none_on_missing)) {
            Py_RETURN_NONE;
        }
        
        PyObject *data = PyTuple_New(0);
        if(!data)
            return (PyObject *)NULL;
        PyObject *tmp = PySeqIter_New(data);
        Py_DECREF(data);
        return tmp;
    }
    if(size >= 0x4000) {
        ptr = (char *)mmap(NULL, size, PROT_READ,
            MAP_SHARED|MAP_NORESERVE|MAP_POPULATE, fd, 0);
        if(ptr == MAP_FAILED)
            ptr = NULL;
    } else {
        Py_BLOCK_THREADS
        fallback = PyString_FromStringAndSize(NULL, size);
        Py_UNBLOCK_THREADS
        if(fallback) {
            errno = 0;
            ptr = (size != read(fd, PyString_AS_STRING(fallback), size)) ?
                MAP_FAILED : NULL;
        }
        int ret = close(fd);
        Py_BLOCK_THREADS
        if(ret) {
            Py_CLEAR(fallback);
            PyErr_SetFromErrnoWithFilenameObject(PyExc_OSError, path);
            return NULL;
        } else if(!fallback) {
            return NULL;
        }
    }
    Py_END_ALLOW_THREADS

    if(ptr == MAP_FAILED) {
        PyErr_SetFromErrnoWithFilenameObject(PyExc_OSError, path);
        if(close(fd))
            PyErr_SetFromErrnoWithFilenameObject(PyExc_OSError, path);
        Py_CLEAR(fallback);
        return NULL;
    }

    self = (pkgcore_readlines *)type->tp_alloc(type, 0);
    if(!self) {
        // you've got to be kidding me...
        if(ptr) {
            munmap(ptr, size);
            close(fd);
            errno = 0;
        } else {
            Py_DECREF(fallback);
        }
        return NULL;
    }
    self->fallback = fallback;
    self->map = ptr;
    if (ptr) {
        self->start = ptr;
        self->fd = fd;
    } else {
        self->start = PyString_AS_STRING(fallback);
        self->fd = -1;
    }
    self->end = self->start + size;

    if(strip_newlines) {
        // die...
        if(PyObject_IsTrue(strip_newlines)) {
            self->strip_newlines = 1;
        } else if(PyErr_Occurred()) {
            Py_DECREF(self);
            return NULL;
        } else {
            self->strip_newlines = 0;
        }
    } else
        self->strip_newlines = 0;
    return (PyObject *)self;
}

static void
pkgcore_readlines_dealloc(pkgcore_readlines *self)
{
    if(self->fallback) {
        Py_DECREF(self->fallback);
    } else if(self->map) {
        if(munmap(self->map, self->end - self->map))
            // swallow it, no way to signal an error
            errno = 0;
        if(close(self->fd))
            // swallow it, no way to signal an error
            errno = 0;
    }
    self->ob_type->tp_free((PyObject *)self);
}

static PyObject *
pkgcore_readlines_iternext(pkgcore_readlines *self)
{
    if(self->start == self->end) {
        // at the end, thus return
        return (PyObject *)NULL;
    }
    char *p = self->start;
    assert(self->end);
    assert(self->start);
    assert(self->map || self->fallback);
    assert(self->end > self->start);

    while(p != self->end && '\n' != *p)
        p++;

    PyObject *ret;
    if(self->strip_newlines) {
        ret = PyString_FromStringAndSize(self->start, p - self->start);
    } else {
        if(p == self->end)
            ret = PyString_FromStringAndSize(self->start, p - self->start);
        else
            ret = PyString_FromStringAndSize(self->start, p - self->start + 1);
    }
    if(p != self->end) {
        p++;
    }
    self->start = p;
    return ret;
}

PyDoc_STRVAR(
    pkgcore_readlines_documentation,
    "readline(path [, strip_newlines [, swallow_missing [, none_on_missing]]])"
    " -> iterable yielding"
    " each line of a file\n\n"
    "if strip_newlines is True, the trailing newline is stripped\n"
    "if swallow_missing is True, for missing files it returns an empty "
    "iterable\n"
    "if none_on_missing and the file is missing, return None instead"
    );

static PyTypeObject pkgcore_readlines_type = {
    PyObject_HEAD_INIT(NULL)
    0,                                               /* ob_size*/
    "pkgcore.util.osutils._posix.readlines",         /* tp_name*/
    sizeof(pkgcore_readlines),                       /* tp_basicsize*/
    0,                                               /* tp_itemsize*/
    (destructor)pkgcore_readlines_dealloc,           /* tp_dealloc*/
    0,                                               /* tp_print*/
    0,                                               /* tp_getattr*/
    0,                                               /* tp_setattr*/
    0,                                               /* tp_compare*/
    0,                                               /* tp_repr*/
    0,                                               /* tp_as_number*/
    0,                                               /* tp_as_sequence*/
    0,                                               /* tp_as_mapping*/
    0,                                               /* tp_hash */
    (ternaryfunc)0,                                  /* tp_call*/
    (reprfunc)0,                                     /* tp_str*/
    0,                                               /* tp_getattro*/
    0,                                               /* tp_setattro*/
    0,                                               /* tp_as_buffer*/
    Py_TPFLAGS_DEFAULT,                              /* tp_flags*/
    pkgcore_readlines_documentation,                 /* tp_doc */
    (traverseproc)0,                                 /* tp_traverse */
    (inquiry)0,                                      /* tp_clear */
    (richcmpfunc)0,                                  /* tp_richcompare */
    0,                                               /* tp_weaklistoffset */
    (getiterfunc)PyObject_SelfIter,                  /* tp_iter */
    (iternextfunc)pkgcore_readlines_iternext,        /* tp_iternext */
    0,                                               /* tp_methods */
    0,                                               /* tp_members */
    0,                                               /* tp_getset */
    0,                                               /* tp_base */
    0,                                               /* tp_dict */
    0,                                               /* tp_descr_get */
    0,                                               /* tp_descr_set */
    0,                                               /* tp_dictoffset */
    (initproc)0,                                     /* tp_init */
    0,                                               /* tp_alloc */
    pkgcore_readlines_new,                           /* tp_new */
};

static PyMethodDef pkgcore_posix_methods[] = {
    {"normpath", (PyCFunction)pkgcore_normpath, METH_O,
        "normalize a path entry"},
    {"join", pkgcore_join, METH_VARARGS,
        "join multiple path items"},
    {"readfile", pkgcore_readfile, METH_VARARGS,
        "fast read of a file: requires a string path, and an optional bool "
        "indicating whether to swallow ENOENT; defaults to false"},
    {NULL}
};

PyDoc_STRVAR(
    pkgcore_posix_documentation,
    "cpython posix path functionality");

PyMODINIT_FUNC
init_posix()
{
    PyObject *m = Py_InitModule3("_posix", pkgcore_posix_methods,
                                 pkgcore_posix_documentation);
    if (!m)
        return;

    if (PyType_Ready(&pkgcore_readlines_type) < 0)
        return;

    Py_INCREF(&pkgcore_readlines_type);
    if (PyModule_AddObject(
            m, "readlines", (PyObject *)&pkgcore_readlines_type) == -1)
        return;

    /* Success! */
}
