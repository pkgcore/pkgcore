/*
 * Copyright: 2006-2009 Brian Harring <ferringb@gmail.com>
 * License: GPL2/BSD
 *
 * C version of some of pkgcore (for extra speed).
 */

/* This does not really do anything since we do not use the "#"
 * specifier in a PyArg_Parse or similar call, but hey, not using it
 * means we are Py_ssize_t-clean too!
 */

#define PY_SSIZE_T_CLEAN

#include <snakeoil/common.h>
#include <structmember.h>

static PyObject *pkgcore_restrictions_type = NULL;
static PyObject *pkgcore_restrictions_subtype = NULL;
static PyObject *pkgcore_match_str = NULL;
static PyObject *pkgcore_handle_exception_str = NULL;

// global
#define NEGATED_RESTRICT    0x1

//strexactmatch
#define CASE_SENSITIVE      0x2

//packagerestriction
#define IGNORE_MISSING      0x2
#define SHALLOW_ATTR        0x4


#define IS_NEGATED(flags) (flags & NEGATED_RESTRICT)


#define PKGCORE_COMMON_RICHCOMPARE(type, self, other, op)   \
{                                                           \
    PyObject *result = NULL;                                \
    if(op != Py_EQ && op != Py_NE) {                        \
        result = Py_NotImplemented;                         \
    } else if(self == other) {                              \
        result = op == Py_EQ ? Py_True : Py_False;          \
    } else if(!PyObject_TypeCheck(other, &type)) {          \
        result = Py_NotImplemented;                         \
    } else if (self->flags != other->flags) {               \
        result = op == Py_NE ? Py_True : Py_False;          \
    }                                                       \
    if(result) {                                            \
        Py_INCREF(result);                                  \
        return result;                                      \
    }                                                       \
}


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


static PyMemberDef pkgcore_StrExactMatch_members[] = {
    {"exact", T_OBJECT, offsetof(pkgcore_StrExactMatch, exact), READONLY},
    {"_hash", T_OBJECT, offsetof(pkgcore_StrExactMatch, hash), READONLY},
    {NULL}
};

snakeoil_IMMUTABLE_ATTR_BOOL(pkgcore_StrExactMatch, "negate", negate,
    (self->flags & NEGATED_RESTRICT))
snakeoil_IMMUTABLE_ATTR_BOOL(pkgcore_StrExactMatch, "case_sensitive", case,
    (self->flags & CASE_SENSITIVE))

static PyGetSetDef pkgcore_StrExactMatch_attrs[] = {
snakeoil_GETSET(pkgcore_StrExactMatch, "negate", negate),
snakeoil_GETSET(pkgcore_StrExactMatch, "case_sensitive", case),
    {NULL}
};


// prototype definition needed to break the ref cycle since the func
// needs the type, type needs the func.
PyObject *
pkgcore_StrExactMatch_richcompare(pkgcore_StrExactMatch *self,
    pkgcore_StrExactMatch *other, int op);


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
    pkgcore_StrExactMatch_members,                   /* tp_members */
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

PyObject *
pkgcore_StrExactMatch_richcompare(pkgcore_StrExactMatch *self,
    pkgcore_StrExactMatch *other, int op)
{
    PKGCORE_COMMON_RICHCOMPARE(pkgcore_StrExactMatch_Type, self, other, op);
    return PyObject_RichCompare(self->exact, other->exact, op);
}

typedef struct {
    PyObject_HEAD
    PyObject *attr;
    PyObject *restriction;
    char flags;
} pkgcore_PackageRestriction;

static int
pkgcore_PackageRestriction_traverse(pkgcore_PackageRestriction *self,
    visitproc visit, void *arg)
{
    Py_VISIT(self->restriction);
    return 0;
}

static PyObject *
pkgcore_PackageRestriction_new(PyTypeObject *type,
    PyObject *args, PyObject *kwds)
{
    pkgcore_PackageRestriction *self = \
        (pkgcore_PackageRestriction *)type->tp_alloc(type, 0);
    if(self) {
        Py_INCREF(Py_None);
        Py_INCREF(Py_None);
        self->attr = self->restriction = Py_None;
        self->flags = 0;
    }
    return (PyObject *)self;
}

static PyObject *
pkgcore_PackageRestriction_breakdown_attr(PyObject *attr)
{
    PyObject *list = NULL, *tup = NULL, *tmp;
    Py_ssize_t x;
    list = PyObject_CallMethod(attr, "split", "s", ".");
    if(list) {
        tup = PyTuple_New(PyList_GET_SIZE(list));
        if(tup) {
            for(x=0; x < PyList_GET_SIZE(list); x++) {
                tmp = PyList_GET_ITEM(list, x);
                Py_INCREF(tmp);
                PyString_InternInPlace(&tmp);
                PyTuple_SET_ITEM(tup, x, tmp);
            }
        }
        Py_DECREF(list);
    }
    return tup;
}

static PyObject *
pkgcore_PackageRestriction_init(pkgcore_PackageRestriction *self,
    PyObject *args, PyObject *kwds)
{
    PyObject *attr, *restriction, *negate = NULL, *ignore_missing = NULL, *tmp = NULL;
    static char *kwdlist[] = {"attr", "childrestriction", "negate",
        "ignore_missing", NULL};
    if(!PyArg_ParseTupleAndKeywords(args, kwds, "SO|OO", kwdlist,
        &attr, &restriction, &negate, &ignore_missing)) {
        return NULL;
    }

    char flags = 0;
    #define make_bool(ptr, statement)                   \
    if((ptr) != Py_True && (ptr) != Py_False) {         \
        if((ptr) != Py_None) {                          \
            int ret = PyObject_IsTrue(ptr);             \
            if(ret == -1)                               \
                return NULL;                            \
            if(ret) { flags |= statement; }             \
        }                                               \
    } else if ((ptr) == Py_True) { flags |= statement;};
    if(negate) {
        make_bool(negate, NEGATED_RESTRICT);
    }
    if(!ignore_missing) {
        flags |= IGNORE_MISSING;
    } else {
        make_bool(ignore_missing, IGNORE_MISSING);
    }
    #undef make_bool
    if(NULL == index(PyString_AS_STRING(attr), '.')) {
        flags |= SHALLOW_ATTR;
        Py_INCREF(attr);
    } else {
        if(!(attr = pkgcore_PackageRestriction_breakdown_attr(attr))) {
            return NULL;
        }
    }
    tmp = self->attr;
    self->attr = attr;
    Py_DECREF(tmp);
    tmp = self->restriction;
    Py_INCREF(restriction);
    self->restriction = restriction;
    Py_DECREF(tmp);
    self->flags = flags;
    return NULL;
}

void
pkgcore_PackageRestriction_dealloc(pkgcore_PackageRestriction *self)
{
    Py_CLEAR(self->attr);
    Py_CLEAR(self->restriction);
    self->ob_type->tp_free((PyObject *)self);
}

static PyObject *
pkgcore_PackageRestriction_pull_attr(pkgcore_PackageRestriction *self,
    PyObject *inst)
{
    Py_ssize_t idx = 0;
    PyObject *tmp = NULL;

    if(self->flags & SHALLOW_ATTR) {
        return PyObject_GetAttr(inst, self->attr);
    }
    Py_INCREF(inst);
    for(; idx < PyTuple_GET_SIZE(self->attr); idx++) {
        tmp = PyObject_GetAttr(inst, PyTuple_GET_ITEM(self->attr, idx));
        Py_DECREF(inst);
        if(!tmp) {
            return tmp;
        }
        inst = tmp;
    }
    return tmp;
}

static PyObject *
pkgcore_PackageRestriction_match(pkgcore_PackageRestriction *self,
    PyObject *inst)
{
    PyObject *result = NULL, *attr;
    attr = pkgcore_PackageRestriction_pull_attr(self, inst);
    if(attr) {
        result = PyObject_CallMethodObjArgs(self->restriction, pkgcore_match_str,
            attr, NULL);
        if(result) {
            int i_result;
            // inline to avoid the VM overhead, then fallback
            if(result == Py_True) {
                i_result = 1;
            } else if (result == Py_False) {
                i_result = 0;
            } else {
                if(-1 == (i_result = PyObject_IsTrue(result))) {
                    Py_DECREF(result);
                    Py_DECREF(attr);
                    return NULL;
                }
            }
            Py_DECREF(result);
            if(IS_NEGATED(self->flags)) {
                result = i_result ? Py_False : Py_True;
            } else {
                result = i_result ? Py_True : Py_False;
            }
            Py_INCREF(result);
        }
        Py_DECREF(attr);
    }
    if(!result) {
        // must ensure it to avoid segfaults...
        if(!PyErr_Occurred()) {
            PyErr_SetString(PyExc_SystemError,
                "NULL result, but no error set");
            return NULL;
        } else if( PyErr_ExceptionMatches(PyExc_KeyboardInterrupt) ||
            PyErr_ExceptionMatches(PyExc_SystemError) ||
            PyErr_ExceptionMatches(PyExc_RuntimeError)) {
            return NULL;
        }
        PyObject *err_type, *err_val, *err_tb;
        PyErr_Fetch(&err_type, &err_val, &err_tb);
        PyErr_NormalizeException(&err_type, &err_val, &err_tb);
        assert(err_val);
        if(!(result = PyObject_CallMethodObjArgs((PyObject *)self,
            pkgcore_handle_exception_str,
            inst, err_val, NULL))) {
            Py_XDECREF(err_type);
            Py_XDECREF(err_val);
            Py_XDECREF(err_tb);
            return NULL;
        }
        int except_i = PyObject_IsTrue(result);
        Py_DECREF(result);
        if(1 == except_i) {
            PyErr_Restore(err_type, err_val, err_tb);
            return NULL;
        }
        Py_XDECREF(err_type);
        Py_XDECREF(err_val);
        Py_XDECREF(err_tb);
        PyErr_Clear();
        result = IS_NEGATED(self->flags) ? Py_True : Py_False;
        Py_INCREF(result);
    }
    return result;
}

PyDoc_STRVAR(
    pkgcore_PackageRestriction_documentation,
    "cpython PackageRestriction base class for speed");

static PyMemberDef pkgcore_PackageRestriction_members[] = {
    {"restriction", T_OBJECT, offsetof(pkgcore_PackageRestriction, restriction), READONLY},
    {"attr", T_OBJECT, offsetof(pkgcore_PackageRestriction, attr), READONLY},
    {NULL}
};

snakeoil_IMMUTABLE_ATTR_BOOL(pkgcore_PackageRestriction, "negate", negate,
    (self->flags & NEGATED_RESTRICT))
snakeoil_IMMUTABLE_ATTR_BOOL(pkgcore_PackageRestriction, "ignore_missing",
    ignore_missing, (self->flags & IGNORE_MISSING))

static PyGetSetDef pkgcore_PackageRestriction_attrs[] = {
snakeoil_GETSET(pkgcore_PackageRestriction, "negate", negate),
snakeoil_GETSET(pkgcore_PackageRestriction, "ignore_missing", ignore_missing),
    {NULL}
};

static PyMethodDef pkgcore_PackageRestriction_methods[] = {
    {"_pull_attr", (PyCFunction)pkgcore_PackageRestriction_pull_attr, METH_O},
    {"match", (PyCFunction)pkgcore_PackageRestriction_match, METH_O},
    {NULL}
};

PyObject *
pkgcore_PackageRestriction_richcompare(pkgcore_PackageRestriction *self,
    pkgcore_PackageRestriction *other, int op);

static PyTypeObject pkgcore_PackageRestriction_Type = {
    PyObject_HEAD_INIT(NULL)
    0,                                              /* ob_size*/
    "pkgcore.restrictions._restrictions.PackageRestriction",
                                                    /* tp_name*/
    sizeof(pkgcore_PackageRestriction),             /* tp_basicsize*/
    0,                                              /* tp_itemsize*/
    (destructor)pkgcore_PackageRestriction_dealloc, /* tp_dealloc*/
    0,                                              /* tp_print*/
    0,                                              /* tp_getattr*/
    0,                                              /* tp_setattr*/
    0,                                              /* tp_compare*/
    0,                                              /* tp_repr*/
    0,                                              /* tp_as_number*/
    0,                                              /* tp_as_sequence*/
    0,                                              /* tp_as_mapping*/
    0,                                              /* tp_hash */
    (ternaryfunc)0,                                 /* tp_call*/
    (reprfunc)0,                                    /* tp_str*/
    0,                                              /* tp_getattro*/
    0,                                              /* tp_setattro*/
    0,                                              /* tp_as_buffer*/
    Py_TPFLAGS_BASETYPE|Py_TPFLAGS_DEFAULT,         /* tp_flags*/
    pkgcore_PackageRestriction_documentation,       /* tp_doc */
    (traverseproc)pkgcore_PackageRestriction_traverse,
                                                    /* tp_traverse */
    (inquiry)0,                                     /* tp_clear */
    (richcmpfunc)pkgcore_PackageRestriction_richcompare,
                                                    /* tp_richcompare */
    0,                                              /* tp_weaklistoffset */
    (getiterfunc)0,                                 /* tp_iter */
    (iternextfunc)0,                                /* tp_iternext */
    pkgcore_PackageRestriction_methods,             /* tp_methods */
    pkgcore_PackageRestriction_members,             /* tp_members */
    pkgcore_PackageRestriction_attrs,               /* tp_getset */
    0,                                              /* tp_base */
    0,                                              /* tp_dict */
    0,                                              /* tp_descr_get */
    0,                                              /* tp_descr_set */
    0,                                              /* tp_dictoffset */
    (initproc)pkgcore_PackageRestriction_init,      /* tp_init */
    0,                                              /* tp_alloc */
    pkgcore_PackageRestriction_new,                 /* tp_new */
};

PyObject *
pkgcore_PackageRestriction_richcompare(pkgcore_PackageRestriction *self,
    pkgcore_PackageRestriction *other, int op)
{
    PKGCORE_COMMON_RICHCOMPARE(pkgcore_PackageRestriction_Type, self, other, op);
    if(self->attr != other->attr) {
        if(op == Py_EQ) {
            Py_RETURN_FALSE;
        }
        Py_RETURN_TRUE;
    }
    PyObject *ret = PyObject_RichCompare(self->attr, other->attr, op);
    if (ret == Py_NotImplemented ||
        ret == (op == Py_EQ ? Py_False : Py_True)) {
        return ret;
    }
    Py_DECREF(ret);
    return PyObject_RichCompare(self->restriction, other->restriction, op);
}


PyDoc_STRVAR(
    pkgcore_restrictions_documentation,
    "cpython restrictions extensions for speed");

PyMODINIT_FUNC
init_restrictions(void)
{
    PyObject *m = Py_InitModule3("_restrictions", NULL,
        pkgcore_restrictions_documentation);
    if (!m)
        return;

    if (PyType_Ready(&pkgcore_StrExactMatch_Type) < 0)
        return;

    if (PyType_Ready(&pkgcore_PackageRestriction_Type) < 0)
        return;

    #define LOAD_STR(ptr, val)                      \
    if(!(ptr)) {                                    \
        if(!((ptr) = PyString_FromString(val))) {   \
            return;                                 \
        }                                           \
    }

    LOAD_STR(pkgcore_restrictions_type, "type");
    LOAD_STR(pkgcore_restrictions_subtype, "subtype");
    LOAD_STR(pkgcore_match_str, "match");
    LOAD_STR(pkgcore_handle_exception_str, "_handle_exception");
    #undef LOAD_STR

    Py_INCREF(&pkgcore_StrExactMatch_Type);
    if (PyModule_AddObject(
            m, "StrExactMatch", (PyObject *)&pkgcore_StrExactMatch_Type) == -1)
        return;

    Py_INCREF(&pkgcore_PackageRestriction_Type);
    if (PyModule_AddObject(
            m, "PackageRestriction",
            (PyObject *)&pkgcore_PackageRestriction_Type) == -1)
        return;

    /* Success! */
}
