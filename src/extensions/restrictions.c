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

#include "common.h"

#define NEGATED_RESTRICT    0x1
#define CASE_SENSITIVE      0x2

#define IS_NEGATED(flags) (flags & NEGATED_RESTRICT)

typedef struct {
    PyObject_HEAD
    PyObject *exact;
    PyObject *hash;
    char flags;
} pkgcore_StrExactMatch;

static void
pkgcore_StrExactMatch_dealloc(pkgcore_StrExactMatch *self)
{
    Py_CLEAR(self->hash);
    Py_DECREF(self->exact);
    self->ob_type->tp_free((PyObject *)self);
}

static PyObject *
pkgcore_StrExactMatch_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    PyObject *exact, *sensitive = NULL, *negate = NULL;

    static char *kwlist[] = {"exact", "case_sensitive", "negate", NULL};
    if(!PyArg_ParseTupleAndKeywords(args, kwds, "O|OO", kwlist,
        &exact, &sensitive, &negate)) {
        return NULL;
    } else if(!PyString_Check(exact) && !PyUnicode_Check(exact)) {
        PyObject *tmp = PyObject_Str(exact);
        if(!tmp)
            return NULL;
        exact = tmp;
    }
    char flags = 0;
    #define set_bool(ptr, statement)        \
    if(ptr) {                               \
        if(ptr == Py_True) {                \
            statement;                      \
        } else if (ptr != Py_False) {       \
            if(PyObject_IsTrue(ptr)) {      \
                statement;                  \
            } else if (PyErr_Occurred()) {  \
                return NULL;                \
            }                               \
        }                                   \
    }
    set_bool(sensitive, flags |= CASE_SENSITIVE)
    else
        flags |= CASE_SENSITIVE;
    set_bool(negate, flags |= NEGATED_RESTRICT);
    #undef set_bool
    
    // alloc now.
    pkgcore_StrExactMatch *self = \
        (pkgcore_StrExactMatch *)type->tp_alloc(type, 0);
    if(!self)
        return NULL;
    self->flags = flags;
    self->hash = NULL;
    if(!(flags & CASE_SENSITIVE)) {
        self->exact = PyObject_CallMethod(exact, "lower", NULL);
        if(!exact)
            Py_CLEAR(self);
    } else {
        Py_INCREF(exact);
        self->exact = exact;
    }
    if(self) {
        PyObject *tmp = PyTuple_New(3);
        if(!tmp) {
            Py_CLEAR(self);
        }
        PyTuple_SET_ITEM(tmp, 0, self->exact);
        PyTuple_SET_ITEM(tmp, 1, IS_NEGATED(self->flags) ? Py_True : Py_False);
        PyTuple_SET_ITEM(tmp, 2, (self->flags & CASE_SENSITIVE) ? 
            Py_True : Py_False);
        long hash = PyObject_Hash(tmp);
        PyTuple_SET_ITEM(tmp, 0, NULL);
        PyTuple_SET_ITEM(tmp, 1, NULL);
        PyTuple_SET_ITEM(tmp, 2, NULL);
        Py_DECREF(tmp);
        if(hash == -1 || !(self->hash = PyLong_FromLong(hash))) {
            Py_DECREF(self);
        }
    }
    return (PyObject *)self;
}

PyObject *
pkgcore_StrExactMatch_richcompare(pkgcore_StrExactMatch *self, 
    pkgcore_StrExactMatch *other, int op)
{
    PyObject *result;
    if(op != Py_EQ && op != Py_NE) {
        result = Py_NotImplemented;
    } else if(self == other) {
        result = op == Py_EQ ? Py_True : Py_False;
    } else if (self->flags != other->flags) {
        result = op == Py_NE ? Py_True : Py_False;
    } else {
        return PyObject_RichCompare(self->exact, other->exact, op);
    }
    Py_INCREF(result);
    return result;
}

static PyObject *
pkgcore_StrExactMatch_match(pkgcore_StrExactMatch *self,
    PyObject *value)
{
    PyObject *real_value = value;
    if(!PyString_Check(value) && !PyUnicode_Check(value)) {
        PyObject *tmp = PyObject_Str(value);
        if(!tmp)
            return tmp;
        real_value = tmp;
    } else
        real_value = value;
    if(!(self->flags & CASE_SENSITIVE)) {
        PyObject *tmp = PyObject_CallMethod(value, "lower", NULL);

        if(real_value != value) {
            Py_DECREF(real_value);
        }

        if(!tmp)
            return NULL;
        real_value = tmp;
    }
    PyObject *ret = PyObject_RichCompare(self->exact, real_value, 
        IS_NEGATED(self->flags) ? Py_NE : Py_EQ);

    if(real_value != value) {
        Py_DECREF(real_value);
    }

    return ret;
}

static PyMethodDef pkgcore_StrExactMatch_methods[] = {
    {"match", (PyCFunction)pkgcore_StrExactMatch_match, METH_O},
    {NULL}
};

PyDoc_STRVAR(
    pkgcore_StrExactMatch_documentation,
    "\nexact string comparison match\n"
    "@param exact: exact basestring to match\n"
    "@keyword case_sensitive: should the match be case sensitive? "
        "(default: True)\n"
    "@keyword negate: should the match results be inverted? (default: False)\n"
    );

PKGCORE_IMMUTABLE_ATTR(pkgcore_StrExactMatch, "exact", exact);
PKGCORE_IMMUTABLE_ATTR(pkgcore_StrExactMatch, "_hash", hash);
PKGCORE_IMMUTABLE_ATTR_BOOL(pkgcore_StrExactMatch, "negate", negate, 
    (self->flags & NEGATED_RESTRICT));
PKGCORE_IMMUTABLE_ATTR_BOOL(pkgcore_StrExactMatch, "case_sensitve", case, 
    (self->flags & CASE_SENSITIVE));

static PyGetSetDef pkgcore_StrExactMatch_attrs[] = {
PKGCORE_GETSET(pkgcore_StrExactMatch, "_hash", hash),
PKGCORE_GETSET(pkgcore_StrExactMatch, "exact", exact),
PKGCORE_GETSET(pkgcore_StrExactMatch, "negate", negate),
PKGCORE_GETSET(pkgcore_StrExactMatch, "case_sensitive", case),
    {NULL}
};

static PyTypeObject pkgcore_StrExactMatch_Type = {
    PyObject_HEAD_INIT(NULL)
    0,                                               /* ob_size*/
    "pkgcore.restrictions._restrictions.StrExactMatch",
                                                     /* tp_name*/
    sizeof(pkgcore_StrExactMatch),                   /* tp_basicsize*/
    0,                                               /* tp_itemsize*/
    (destructor)pkgcore_StrExactMatch_dealloc,       /* tp_dealloc*/
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
    Py_TPFLAGS_BASETYPE|Py_TPFLAGS_DEFAULT,                              /* tp_flags*/
    pkgcore_StrExactMatch_documentation,             /* tp_doc */
    (traverseproc)0,                                 /* tp_traverse */
    (inquiry)0,                                      /* tp_clear */
    (richcmpfunc)pkgcore_StrExactMatch_richcompare,  /* tp_richcompare */
    0,                                               /* tp_weaklistoffset */
    (getiterfunc)0,                                  /* tp_iter */
    (iternextfunc)0,                                 /* tp_iternext */
    pkgcore_StrExactMatch_methods,                   /* tp_methods */
    0,                                               /* tp_members */
    pkgcore_StrExactMatch_attrs,                     /* tp_getset */
    0,                                               /* tp_base */
    0,                                               /* tp_dict */
    0,                                               /* tp_descr_get */
    0,                                               /* tp_descr_set */
    0,                                               /* tp_dictoffset */
    (initproc)0,                                     /* tp_init */
    0,                                               /* tp_alloc */
    pkgcore_StrExactMatch_new,                       /* tp_new */
};

PyDoc_STRVAR(
    pkgcore_restrictions_documentation,
    "cpython restrictions extensions for speed");

PyMODINIT_FUNC
init_restrictions()
{
    if (PyType_Ready(&pkgcore_StrExactMatch_Type) < 0)
        return;
    
    PyObject *m = Py_InitModule3("_restrictions", NULL,
        pkgcore_restrictions_documentation);
    
    Py_INCREF(&pkgcore_StrExactMatch_Type);
    PyModule_AddObject(m, "StrExactMatch",
        (PyObject *)&pkgcore_StrExactMatch_Type);
    
    if (PyErr_Occurred())
        Py_FatalError("can't initialize module _restrictions");
}
