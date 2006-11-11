/*
 * Copyright: 2006 Brian Harring <ferringb@gmail.com>
 * License: GPL2
 *
 * common macros.
 */

#ifndef PKGCORE_COMMON_HEADER
#define PKGCORE_COMMON_HEADER 1

#define PKGCORE_IMMUTABLE_ATTRIBUTE(type, getter, setter, name,         \
attribute)                                                              \
static int                                                              \
setter (type *self, PyObject *v, void *closure)                         \
{                                                                       \
    PyErr_SetString(PyExc_AttributeError, name" is immutable");         \
    return -1;                                                          \
};                                                                      \
                                                                        \
static PyObject *                           \
getter (type *self, void *closure)          \
{                                           \
    if (self->attribute == NULL) {          \
        Py_RETURN_NONE;                     \
    }                                       \
    Py_INCREF(self->attribute);             \
    return self->attribute;                 \
}

#endif
