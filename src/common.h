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

#define PKGCORE_IMMUTABLE_ATTR_BOOL(type, name, attr, test)             \
static int                                                              \
type##_set_##attr (type *self, PyObject *v, void *closure)              \
{                                                                       \
    PyErr_SetString(PyExc_AttributeError, name" is immutable");         \
    return -1;                                                          \
}                                                                       \
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


#define PKGCORE_FUNC_DESC(meth_name, class_name, func, methargs)        \
_PKGCORE_FUNC_DESC(meth_name, class_name, func, methargs, 0)
#define _PKGCORE_FUNC_DESC(meth_name, class_name, func, methargs, desc) \
                                                                        \
static PyTypeObject func##_type = {                                     \
    PyObject_HEAD_INIT(NULL)                                            \
    0,                                  /* ob_size        */            \
    class_name,                         /* tp_name        */            \
    sizeof(PyObject),                   /* tp_basicsize   */            \
    0,                                  /* tp_itemsize    */            \
    0,                                  /* tp_dealloc     */            \
    0,                                  /* tp_print       */            \
    0,                                  /* tp_getattr     */            \
    0,                                  /* tp_setattr     */            \
    0,                                  /* tp_compare     */            \
    0,                                  /* tp_repr        */            \
    0,                                  /* tp_as_number   */            \
    0,                                  /* tp_as_sequence */            \
    0,                                  /* tp_as_mapping  */            \
    0,                                  /* tp_hash      */              \
    (ternaryfunc)func,                  /* tp_call      */              \
    0,                                  /* tp_str       */              \
    0,                                  /* tp_getattro  */              \
    0,                                  /* tp_setattro  */              \
    0,                                  /* tp_as_buffer */              \
    Py_TPFLAGS_DEFAULT,                 /* tp_flags     */              \
    "cpython version of "#meth_name,   /* tp_doc       */               \
    0,                                  /* tp_traverse  */              \
    0,                                  /* tp_clear     */              \
    0,                                  /* tp_richcompare    */         \
    0,                                  /* tp_weaklistoffset */         \
    0,                                  /* tp_iter      */              \
    0,                                  /* tp_iternext  */              \
    0,                                  /* tp_methods   */              \
    0,                                  /* tp_members   */              \
    0,                                  /* tp_getset    */              \
    0,                                  /* tp_base      */              \
    0,                                  /* tp_dict      */              \
    desc,                               /* tp_descr_get */              \
    0,                                  /* tp_descr_set */              \
}; 

#define PKGCORE_FUNC_BINDING(meth_name, class_name, func, methargs)    \
static PyObject *                                                       \
func##_get_descr(PyObject *self, PyObject *obj, PyObject *type)         \
{                                                                       \
    static PyMethodDef mdef = {meth_name, (PyCFunction)func, methargs,  \
        NULL};                                                          \
    return PyCFunction_New(&mdef, obj);                                 \
}                                                                       \
                                                                        \
_PKGCORE_FUNC_DESC(meth_name, class_name, func, methargs,               \
    func##_get_descr)

#endif
