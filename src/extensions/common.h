/*
 * Copyright: 2006 Brian Harring <ferringb@gmail.com>
 * License: GPL2
 *
 * common macros.
 */

#ifndef PKGCORE_COMMON_HEADER
#define PKGCORE_COMMON_HEADER 1

#include <Python.h>
#include "py24-compatibility.h"

#define RAW_PKGCORE_IMMUTABLE_ATTR(type, name, attr, ret)               \
static int                                                              \
type##_set_##attr (type *self, PyObject *v, void *closure)              \
{                                                                       \
    PyErr_SetString(PyExc_AttributeError, name" is immutable");         \
    return -1;                                                          \
};                                                                      \
                                                                        \
static PyObject *                                                       \
type##_get_##attr (type *self, void *closure)                           \
{                                                                       \
    if (self->attr == NULL) {                                           \
        Py_INCREF(ret);                                                 \
        return ret;                                                     \
    }                                                                   \
    Py_INCREF(self->attr);                                              \
    return self->attr;                                                  \
}

#define PKGCORE_GETSET(type, doc, attr)         \
    {doc, (getter)type##_get_##attr ,           \
        (setter)type##_set_##attr , NULL}

#define PKGCORE_IMMUTABLE_ATTR(type, name, attr)  \
RAW_PKGCORE_IMMUTABLE_ATTR(type, name, attr, Py_None)

#define PKGCORE_IMMUTABLE_ATTR_BOOL(type, name, attr, test)             \
static int                                                              \
type##_set_##attr (type *self, PyObject *v, void *closure)              \
{                                                                       \
    PyErr_SetString(PyExc_AttributeError, name" is immutable");         \
    return -1;                                                          \
};                                                                      \
                                                                        \
static PyObject *                                                       \
type##_get_##attr (type *self, void *closure)                           \
{                                                                       \
    PyObject *s = (test) ? Py_True : Py_False;                          \
    Py_INCREF(s);                                                       \
    return s;                                                           \
}

#define PKGCORE_GETSET(type, doc, attr)         \
    {doc, (getter)type##_get_##attr ,           \
        (setter)type##_set_##attr , NULL}

#endif
