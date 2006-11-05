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
#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>

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
//    Py_ssize_t old_len;
    for(i = start; i < end; i++) {
        // this is safe because we're using CheckExact above.
        s_start = s = PyString_AS_STRING(items[i]);
//        old_len = len;
        while('\0' != *s)
            s++;
        len += s - s_start;
        s_start++;
        char *s_end = s;
        if(i + 1 != end) {
            while(s != s_start && '/' == s[-1])
                s--;
            if(s_end == s && s_start != s) {
                len++;
            } else if(s_start != s) {
                len -= s_end - s -1;
            }
        }
//        printf("adding %i for %s\n", len - old_len,
//            PyString_AS_STRING(items[i]));
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
//    printf("ended at %i, len %i, '%s'\n", buf - PyString_AS_STRING(ret),
//        len, PyString_AS_STRING(ret));
    // resize it now.
    return ret;
}

static PyObject *
pkgcore_readfile(PyObject *self, PyObject *args)
{
    PyObject *path, *swallow_missing;
    if(!args || !PyArg_ParseTuple(args, "S|O:readfile", &path,
        &swallow_missing)) {
        return (PyObject *)NULL;
    }
    errno = 0;
    int fd = open(PyString_AS_STRING(path), O_LARGEFILE);
    if(fd < 0) {
        if(errno == ENOENT) {
            if(swallow_missing && PyObject_IsTrue(swallow_missing)) {
                errno = 0;
                Py_RETURN_NONE;
            }
        }
        return PyErr_SetFromErrnoWithFilenameObject(PyExc_OSError, path);
    }
    PyObject *ret = NULL;
    struct stat st;
    if(fstat(fd, &st)) {
        ret = PyErr_SetFromErrno(PyExc_OSError);
        goto cleanup;
    } else if(S_ISDIR(st.st_mode)) {
        errno = EISDIR;
        ret = PyErr_SetFromErrnoWithFilenameObject(PyExc_OSError, path);
        goto cleanup;
    }
    ret = PyString_FromStringAndSize(NULL, (Py_ssize_t)st.st_size);
    if(ret) {
        if(st.st_size != read(fd, PyString_AS_STRING(ret), st.st_size)) {
            Py_CLEAR(ret);
            ret = PyErr_SetFromErrnoWithFilenameObject(PyExc_IOError, path);
        }
    }
    cleanup:
    if(close(fd)) {
        Py_CLEAR(ret);
        ret = PyErr_SetFromErrnoWithFilenameObject(PyExc_OSError, path);
    }
    return ret;
}

static PyMethodDef pkgcore_path_methods[] = {
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
    pkgcore_path_documentation,
    "cpython posix path functionality");

PyMODINIT_FUNC
init_path()
{
    Py_InitModule3("_path", pkgcore_path_methods,
        pkgcore_path_documentation);
}
