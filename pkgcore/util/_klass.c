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

typedef struct {
    PyObject_HEAD
    PyObject *redirect_target;
} pkgcore_GetAttrProxy;

static void
pkgcore_GetAttrProxy_dealloc(pkgcore_GetAttrProxy *self)
{
    Py_CLEAR(self->redirect_target);
    self->ob_type->tp_free((PyObject *)self);
}

static PyObject *
pkgcore_GetAttrProxy_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    pkgcore_GetAttrProxy *self;
    PyObject *alias_attr;

    if(!PyArg_ParseTuple(args, "S:__new__", &alias_attr))
        return NULL;
    self = (pkgcore_GetAttrProxy *)type->tp_alloc(type, 0);

    if (self) {
        self->redirect_target = alias_attr;
        Py_INCREF(alias_attr);
    }
    return (PyObject *)self;
}

static PyObject *
pkgcore_GetAttrProxy_call(pkgcore_GetAttrProxy *self, PyObject *args,
    PyObject *kwds)
{
    PyObject *attr, *real_obj, *tmp;

    if(!PyArg_ParseTuple(args, "OS:__call__", &real_obj, &attr))
        return NULL;
    real_obj = PyObject_GenericGetAttr(real_obj, self->redirect_target);
    if(!real_obj)
        return NULL;

    tmp = PyObject_GetAttr(real_obj, attr);
    Py_DECREF(real_obj);
    return (PyObject *)tmp;
}


static PyTypeObject pkgcore_GetAttrProxyType = {
    PyObject_HEAD_INIT(NULL)
    0,                                               /* ob_size */
    "pkgcore.util._klass.GetAttrProxy",              /* tp_name */
    sizeof(pkgcore_GetAttrProxy),                    /* tp_basicsize */
    0,                                               /* tp_itemsize */
    (destructor)pkgcore_GetAttrProxy_dealloc,        /* tp_dealloc */
    0,                                               /* tp_print */
    0,                                               /* tp_getattr */
    0,                                               /* tp_setattr */
    0,                                               /* tp_compare */
    0,                                               /* tp_repr */
    0,                                               /* tp_as_number */
    0,                                               /* tp_as_sequence */
    0,                                               /* tp_as_mapping */
    0,                                               /* tp_hash  */
    (ternaryfunc)pkgcore_GetAttrProxy_call,          /* tp_call */
    (reprfunc)0,                                     /* tp_str */
    0,                                               /* tp_getattro */
    0,                                               /* tp_setattro */
    0,                                               /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,         /* tp_flags */
    "GetAttrProxy object; used mainly for native __getattr__ speed",
                                                     /* tp_doc */
    0,                                               /* tp_traverse */
    0,                                               /* tp_clear */
    0,                                               /* tp_richcompare */
    0,                                               /* tp_weaklistoffset */
    0,                                               /* tp_iter */
    0,                                               /* tp_iternext */
    0,                                               /* tp_methods */
    0,                                               /* tp_members */
    0,                                               /* tp_getset */
    0,                                               /* tp_base */
    0,                                               /* tp_dict */
    0,                                               /* tp_descr_get */
    0,                                               /* tp_descr_set */
    0,                                               /* tp_dictoffset */
    0,                                               /* tp_init */
    0,                                               /* tp_alloc */
    pkgcore_GetAttrProxy_new,                        /* tp_new */

};

PyDoc_STRVAR(
    pkgcore_klass_documentation,
    "misc cpython class functionality");

PyMODINIT_FUNC
init_klass()
{
    if (PyType_Ready(&pkgcore_GetAttrProxyType) < 0)
        return;

    PyObject *m = Py_InitModule3("_klass", NULL,
        pkgcore_klass_documentation);

    Py_INCREF(&pkgcore_GetAttrProxyType);
    PyModule_AddObject(m, "GetAttrProxy",
        (PyObject *)&pkgcore_GetAttrProxyType);
}
