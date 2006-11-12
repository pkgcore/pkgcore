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

#define PKGCORE_IMMUTABLE_ATTRIBUTE(type, name, attr)                   \
static int                                                              \
type##_set_##attr (type *self, PyObject *v, void *closure)          \
{                                                                       \
    PyErr_SetString(PyExc_AttributeError, name" is immutable");         \
    return -1;                                                          \
};                                                                      \
                                                                        \
static PyObject *                                   \
type##_get_##attr (type *self, void *closure)   \
{                                                   \
    if (self->attr == NULL) {                       \
        Py_RETURN_NONE;                             \
    }                                               \
    Py_INCREF(self->attr);                          \
    return self->attr;                              \
}

#define PKGCORE_GETSET(type, doc, attr)           \
    {doc, (getter)type##_get_##attr ,           \
        (setter)type##_set_##attr , NULL}

#endif
