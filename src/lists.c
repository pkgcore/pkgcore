/*
 * Copyright: 2006 Marien Zwart <marienz@gentoo.org>
 * License: GPL2
 *
 * C version of some of pkgcore (for extra speed).
 */

/* This does not really do anything since we do not use the "#"
 * specifier in a PyArg_Parse or similar call, but hey, not using it
 * means we are Py_ssize_t-clean too!
 */

#define PY_SSIZE_T_CLEAN

#include "Python.h"
#include "py24-compatibility.h"


/* Helper functions */

static PyObject *
build_initial_iterables(PyObject *l) {
    PyObject *result, *iter = PyObject_GetIter(l);
    if (!iter)
        return NULL;

    result = PyList_New(1);
    if (!result) {
        Py_DECREF(iter);
        return NULL;
    }
    PyList_SET_ITEM(result, 0, iter);
    return result;
}

/* iflatten_func: recursively flatten an iterable with a func as filter. */

typedef struct {
    PyObject_HEAD
    PyObject *skip_func;
    PyObject *iterables;
    char in_iternext;
} pkgcore_iflatten_func;

static void
pkgcore_iflatten_func_dealloc(pkgcore_iflatten_func *self)
{
    Py_CLEAR(self->skip_func);
    Py_CLEAR(self->iterables);
    self->ob_type->tp_free((PyObject*) self);
}

static PyObject *
pkgcore_iflatten_func_new(PyTypeObject *type,
                              PyObject *args, PyObject *kwargs)
{
    pkgcore_iflatten_func *self;
    PyObject *l=NULL, *skip_func=NULL, *tmp;
    int res;

    if (kwargs && PyDict_Size(kwargs)) {
        PyErr_SetString(PyExc_TypeError,
                        "iflatten_func takes no keyword arguments");
        return NULL;
    }
    if (!PyArg_UnpackTuple(args, "iflatten_func", 2, 2, &l, &skip_func)) {
        return NULL;
    }

    /* Check if we got a single argument that should be skipped. */
    tmp = PyObject_CallFunctionObjArgs(skip_func, l, NULL);
    if (!tmp) {
        return NULL;
    }
    res = PyObject_IsTrue(tmp);
    Py_DECREF(tmp);
    if (res == -1) {
        return NULL;
    } else if (res) {
        PyObject *tuple = PyTuple_Pack(1, l);
        if (!tuple) {
            return NULL;
        }
        PyObject *iter = PyObject_GetIter(tuple);
        Py_DECREF(tuple);
        return iter;
    }

    self = (pkgcore_iflatten_func *)type->tp_alloc(type, 0);
    if (!self)
        return NULL;

    self->in_iternext = 0;

    if (!(self->iterables = build_initial_iterables(l))) {
        Py_DECREF(self);
        return NULL;
    }

    Py_INCREF(skip_func);
    self->skip_func = skip_func;

    return (PyObject *)self;
}

static PyObject *
pkgcore_iflatten_func_iternext(pkgcore_iflatten_func *self) {
    PyObject *tail, *result, *tmp;
    int res;
    Py_ssize_t n;

    if (self->in_iternext) {
        /* We do not allow this because it means our list could be
         * manipulated while we are running. Exception raised matches
         * what a generator raises if you try the same thing.
         */
        PyErr_SetString(PyExc_ValueError,
                        "Recursive calls to iflatten_func.next are illegal");
        return NULL;
    }
    self->in_iternext = 1;

    /* Look at the final iterator on our stack: */
    while ((n = PyList_GET_SIZE(self->iterables))) {
        tail = PyList_GET_ITEM(self->iterables, n - 1);

        /* See if it has any results left: */

        /* (This reference is borrowed from the list, but since we
           disallow recursive calls in here it should be safe to not
           increment it). */

        result = PyIter_Next(tail);
        if (result) {

            /* See if we need to iterate over this new result: */

            tmp = PyObject_CallFunctionObjArgs(self->skip_func, result, NULL);
            if (!tmp) {
                Py_DECREF(result);
                self->in_iternext = 0;
                return NULL;
            }
            res = PyObject_IsTrue(tmp);
            Py_DECREF(tmp);
            if (res == -1) {
                Py_DECREF(result);
                result = NULL;
            } else if (!res) {
                /* False from our skip func. */
                /* If it is an iterator add it to our chain, else return it. */
                tmp = PyObject_GetIter(result);
                if (tmp) {
                    /* Iterable, append to our stack and continue. */
                    Py_DECREF(result);
                    result = NULL;
                    res = PyList_Append(self->iterables, tmp);
                    Py_DECREF(tmp);
                    if (res != -1) {
                        continue;
                    }
                    /* Fall through and propagate the error. */
                } else {
                    /* If we get here PyObject_GetIter raised an exception.
                     * If it was TypeError we have a non-iterator we can
                     * just return, else we propagate the error.
                     */
                    if (PyErr_ExceptionMatches(PyExc_TypeError)) {
                        PyErr_Clear();
                    } else {
                        Py_DECREF(result);
                        result = NULL;
                    }
                }
            }
        } else {
            /* PyIter_Next did not return an item. If this was not
             * because of an error we should pop the exhausted
             * iterable off and continue. */
            if (!PyErr_Occurred() &&
                PySequence_DelItem(self->iterables, n - 1) != -1) {
                continue;
            }
        }
        self->in_iternext = 0;
        return result;
    }

    /* We ran out of iterables entirely, so we are done */
    self->in_iternext = 0;
    return NULL;
}

PyDoc_STRVAR(
    pkgcore_iflatten_func_documentation,
    "iflatten_func(iters, func): collapse [(1),2] into [1,2]\n"
    "\n"
    "func is called with one argument and should return true if this \n"
    "should not be iterated over.\n"
    );

static PyTypeObject pkgcore_iflatten_func_type = {
    PyObject_HEAD_INIT(NULL)
    0,                                               /* ob_size*/
    "pkgcore.util._lists.iflatten_func",             /* tp_name*/
    sizeof(pkgcore_iflatten_func),                   /* tp_basicsize*/
    0,                                               /* tp_itemsize*/
    (destructor)pkgcore_iflatten_func_dealloc,       /* tp_dealloc*/
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
    pkgcore_iflatten_func_documentation,             /* tp_doc */
    (traverseproc)0,                                 /* tp_traverse */
    (inquiry)0,                                      /* tp_clear */
    (richcmpfunc)0,                                  /* tp_richcompare */
    0,                                               /* tp_weaklistoffset */
    (getiterfunc)PyObject_SelfIter,                  /* tp_iter */
    (iternextfunc)pkgcore_iflatten_func_iternext,    /* tp_iternext */
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
    pkgcore_iflatten_func_new,                       /* tp_new */
};

/* iflatten_instance: recursively flatten an iterable
   except for some instances */

typedef struct {
    PyObject_HEAD
    PyObject *skip_flattening;
    PyObject *iterables;
    char in_iternext;
} pkgcore_iflatten_instance;

static void
pkgcore_iflatten_instance_dealloc(pkgcore_iflatten_instance *self)
{
    Py_CLEAR(self->skip_flattening);
    Py_CLEAR(self->iterables);
    self->ob_type->tp_free((PyObject*) self);
}

static PyObject *
pkgcore_iflatten_instance_new(PyTypeObject *type,
                                  PyObject *args, PyObject *kwargs)
{
    pkgcore_iflatten_instance *self;
    PyObject *l=NULL, *skip_flattening=(PyObject*)&PyBaseString_Type;
    int res;

    if (kwargs && PyDict_Size(kwargs)) {
        PyErr_SetString(PyExc_TypeError,
                        "iflatten_instance takes no keyword arguments");
        return NULL;
    }
    if (!PyArg_UnpackTuple(args, "iflatten_instance", 1, 2,
                           &l, &skip_flattening)) {
        return NULL;
    }

    /* Check if we got a single argument that should be skipped. */
    res = PyObject_IsInstance(l, skip_flattening);
    if (res == -1) {
        return NULL;
    } else if (res) {
        PyObject *tuple = PyTuple_Pack(1, l);
        if (!tuple) {
            return NULL;
        }
        PyObject *iter = PyObject_GetIter(tuple);
        Py_DECREF(tuple);
        return iter;
    }

    self = (pkgcore_iflatten_instance *)type->tp_alloc(type, 0);
    if (!self)
        return NULL;

    self->in_iternext = 0;

    if (!(self->iterables = build_initial_iterables(l))) {
        Py_DECREF(self);
        return NULL;
    }

    Py_INCREF(skip_flattening);
    self->skip_flattening = skip_flattening;

    return (PyObject *)self;
}

static PyObject *
pkgcore_iflatten_instance_iternext(pkgcore_iflatten_instance *self) {
    PyObject *tail, *result, *iter;
    int n, res;

    if (self->in_iternext) {
        /* We do not allow this because it means our list could be
         * manipulated while we are running. Exception raised matches
         * what a generator raises if you try the same thing.
         */
        PyErr_SetString(
            PyExc_ValueError,
            "Recursive calls to iflatten_instance.next are illegal");
        return NULL;
    }
    self->in_iternext = 1;

    /* Look at the final iterator on our stack: */

    while ((n = PyList_GET_SIZE(self->iterables))) {
        tail = PyList_GET_ITEM(self->iterables, n - 1);

        /* See if it has any results left: */
        /* (This reference is borrowed from the list, but since we
           disallow recursive calls in here it should be safe to not
           increment it). */

        result = PyIter_Next(tail);
        if (result) {
            /* See if we need to iterate over this new result: */

            res = PyObject_IsInstance(result, self->skip_flattening);
            if (res == -1) {
                Py_DECREF(result);
                result = NULL;
            } else if (!res) {
                /* Not in skip_flattening. */
                /* If it is an iterator add it to our chain, else return it. */
                iter = PyObject_GetIter(result);
                if (iter) {
                    /* Iterable, append to our stack and continue. */
                    Py_DECREF(result);
                    result = NULL;
                    res = PyList_Append(self->iterables, iter);
                    Py_DECREF(iter);
                    if (res != -1) {
                        continue;
                    }
                    /* Fall through and propagate the error. */
                } else {
                    /* If we get here PyObject_GetIter raised an exception.
                     * If it was TypeError we have a non-iterator we can
                     * just return, else we propagate the error.
                     */
                    if (PyErr_ExceptionMatches(PyExc_TypeError)) {
                        PyErr_Clear();
                    } else {
                        Py_DECREF(result);
                        result = NULL;
                    }
                }
            }
        } else {
            /* PyIter_Next did not return an item. If this was not
             * because of an error we should pop the exhausted
             * iterable off and continue. */
            if (!PyErr_Occurred() &&
                PySequence_DelItem(self->iterables, n - 1) != -1) {
                continue;
            }
        }
        self->in_iternext = 0;
        return result;
    }

    /* We ran out of iterables entirely, so we are done */
    self->in_iternext = 0;
    return NULL;
}

PyDoc_STRVAR(
    pkgcore_iflatten_instance_documentation,
    "iflatten_func(iters, skip_flattening=basestring)\n"
    "\n"
    "collapse [(1),2] into [1,2]\n"
    "skip_flattening is a list of classes to not descend through\n"
    );

static PyTypeObject pkgcore_iflatten_instance_type = {
    PyObject_HEAD_INIT(NULL)
    0,                                               /* ob_size*/
    "pkgcore.util._lists.iflatten_instance",         /* tp_name*/
    sizeof(pkgcore_iflatten_instance),               /* tp_basicsize*/
    0,                                               /* tp_itemsize*/
    (destructor)pkgcore_iflatten_instance_dealloc,   /* tp_dealloc*/
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
    pkgcore_iflatten_instance_documentation,         /* tp_doc */
    (traverseproc)0,                                 /* tp_traverse */
    (inquiry)0,                                      /* tp_clear */
    (richcmpfunc)0,                                  /* tp_richcompare */
    0,                                               /* tp_weaklistoffset */
    (getiterfunc)PyObject_SelfIter,                  /* tp_iter */
    (iternextfunc)pkgcore_iflatten_instance_iternext, /* tp_iternext */
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
    pkgcore_iflatten_instance_new,                   /* tp_new */
};


/* Initialization function for the module */

PyDoc_STRVAR(
    pkgcore_lists_documentation,
    "C reimplementation of some of pkgcore.util.lists.");

PyMODINIT_FUNC
init_lists()
{
    /* Create the module and add the functions */
    PyObject *m = Py_InitModule3("_lists", NULL, pkgcore_lists_documentation);
    if (!m)
        return;

    if (PyType_Ready(&pkgcore_iflatten_func_type) < 0)
        return;

    if (PyType_Ready(&pkgcore_iflatten_instance_type) < 0)
        return;

    Py_INCREF(&pkgcore_iflatten_func_type);
    if (PyModule_AddObject(
            m, "iflatten_func", (PyObject *)&pkgcore_iflatten_func_type) == -1)
        return;

    Py_INCREF(&pkgcore_iflatten_instance_type);
    if (PyModule_AddObject(
            m, "iflatten_instance",
            (PyObject *)&pkgcore_iflatten_instance_type) == -1)
        return;
}
