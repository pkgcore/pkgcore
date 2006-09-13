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

/* Compatibility with python < 2.5 */

#if PY_VERSION_HEX < 0x02050000
typedef int Py_ssize_t;
#define PY_SSIZE_T_MAX INT_MAX
#define PY_SSIZE_T_MIN INT_MIN
#endif


/* Helper functions */

static PyObject *
build_initial_iterables(PyObject *l) {
    /* Build the initial "iterables" of [iter((l,))].
     * We use this instead of simply [iter(l)] because "l" might be a thing
     * we cannot iterate over (list(iflatten_instance(42)) should be [42], and
     * more importantly list(iflatten_instance((1, 2), (tuple,))) should be
     * [(1, 2)]).
     */
    PyObject *result, *iter, *inner = PyTuple_Pack(1, l);
    if (!inner)
        return NULL;

    iter = PyObject_GetIter(inner);
    Py_DECREF(inner);
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
    PyObject *l=NULL, *skip_func=NULL;

    if (kwargs) {
        PyErr_SetString(PyExc_TypeError,
                        "iflatten_func takes no keyword arguments");
        return NULL;
    }
    if (!PyArg_ParseTuple(args, "OO", &l, &skip_func))
        return NULL;

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
         * manipulated while we are running. */
        /* TODO which exception makes sense here */
        PyErr_SetString(PyExc_Exception,
                        "Recursive calls to iflatten_func.next are illegal");
        return NULL;
    }
    self->in_iternext = 1;

    /* Look at the final iterator on our stack: */
    while(n = PyList_GET_SIZE(self->iterables)) {
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
    "collapse [(1),2] into [1,2]\n"
    "\n"
    "@param skip_flattening: list of classes to not descend through\n"
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

    if (kwargs) {
        PyErr_SetString(PyExc_TypeError,
                        "iflatten_instance takes no keyword arguments");
        return NULL;
    }
    if (!PyArg_ParseTuple(args, "O|O", &l, &skip_flattening))
        return NULL;

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
         * manipulated while we are running. */
        /* TODO which exception makes sense here */
        PyErr_SetString(
            PyExc_Exception,
            "Recursive calls to iflatten_instance.next are illegal");
        return NULL;
    }
    self->in_iternext = 1;

    /* Look at the final iterator on our stack: */

    while(n = PyList_GET_SIZE(self->iterables)) {
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
    "collapse [(1),2] into [1,2]\n"
    "\n"
    "@param skip_flattening: list of classes to not descend through\n"
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
    PyObject *m;

    if (PyType_Ready(&pkgcore_iflatten_func_type) < 0)
        return;

    if (PyType_Ready(&pkgcore_iflatten_instance_type) < 0)
        return;

    /* Create the module and add the functions */
    m = Py_InitModule3("_lists", NULL, pkgcore_lists_documentation);

    Py_INCREF(&pkgcore_iflatten_func_type);
    PyModule_AddObject(m, "iflatten_func",
                       (PyObject *)&pkgcore_iflatten_func_type);

    Py_INCREF(&pkgcore_iflatten_instance_type);
    PyModule_AddObject(m, "iflatten_instance",
                       (PyObject *)&pkgcore_iflatten_instance_type);

    /* Check for errors */
    if (PyErr_Occurred())
        Py_FatalError("can't initialize module _lists");
}
