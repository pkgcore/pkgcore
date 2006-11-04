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
    
    PyObject *new_path = PyString_FromStringAndSize(NULL, len + 1);
    if(!new_path)
        return new_path;
    real_newstart = newstart = newp = PyString_AsString(new_path);
    
    #define SKIP_SLASHES(ptr) while('/' == *(ptr)) (ptr)++;

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

    #undef SKIP_SLASHES
    *newp = '\0';
    // protect leading slash, but strip trailing.
    --newp;
    while(newp > real_newstart && '/' == *newp)
        newp--;

    // resize it now.
    _PyString_Resize(&new_path, newp - real_newstart + 1);
    return new_path;
}

static PyMethodDef pkgcore_path_methods[] = {
    {"normpath", (PyCFunction)pkgcore_normpath, METH_O,
        "normalize a path entry"},
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
