/*
 * Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
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

// exceptions, loaded during initialization.
static PyObject *pkgcore_depset_ParseErrorExc = NULL;
static PyObject *pkgcore_depset_ValContains = NULL;
static PyObject *pkgcore_depset_PkgCond = NULL;
static PyObject *pkgcore_depset_PkgAnd = NULL;
static PyObject *pkgcore_depset_PkgOr = NULL;

#define ISDIGIT(c) ('0' <= (c) && '9' >= (c))
#define ISALPHA(c) (('a' <= (c) && 'z' >= (c)) || ('A' <= (c) && 'Z' >= (c)))
#define ISLOWER(c) ('a' <= (c) && 'z' >= (c))
#define ISALNUM(c) (ISALPHA(c) || ISDIGIT(c))

static void
_Err_SetParse(PyObject *dep_str, PyObject *msg, char *tok_start, char *tok_end)
{
    PyObject *ret;
    PyObject *args = Py_BuildValue("(S)", dep_str);
    if(!args)
        return;
    PyObject *kwds = Py_BuildValue("{sSss#}", "msg", msg,
        "token", tok_start, tok_end - tok_start);
    if(kwds) {
        ret = PyObject_Call(pkgcore_depset_ParseErrorExc, args, kwds);
        if(ret) {
            PyErr_SetObject(pkgcore_depset_ParseErrorExc, ret);
            Py_DECREF(ret);
        }
        Py_DECREF(kwds);
    }
    Py_DECREF(args);
}

static void
Err_WrapException(PyObject *dep_str, char *tok_start,
    char *tok_end)
{
    PyObject *type, *val, *tb;
    PyErr_Fetch(&type, &val, &tb);
    if(val) {
        _Err_SetParse(dep_str, val, tok_start, tok_end);
    }
    Py_XDECREF(type);
    Py_XDECREF(val);
    Py_XDECREF(tb);
}

static void
Err_SetParse(PyObject *dep_str, char *msg, char *tok_start, char *tok_end)
{
    PyObject *s = PyString_FromString(msg);
    if(!s)
        return;
    _Err_SetParse(dep_str, s, tok_start, tok_end);
    Py_DECREF(s);
}

static inline PyObject *
make_use_conditional(char *use_start, char *use_end, PyObject *payload)
{
    PyObject *val;
    if('!' == *use_start) {
        PyObject *kwds = Py_BuildValue("{sO}", "negate", Py_True);
        if(!kwds)
            return NULL;
        PyObject *args = Py_BuildValue("(s#)", use_start + 1,
            use_end - use_start -1);
        if(!args) {
            Py_DECREF(kwds);
            return NULL;
        }
        val = PyObject_Call(pkgcore_depset_ValContains, args, kwds);
        Py_DECREF(args);
        Py_DECREF(kwds);
    } else {
        val = PyObject_CallFunction(pkgcore_depset_ValContains, "s#",
            use_start, use_end - use_start);
    }
    if(!val)
        return NULL;

    PyObject *restriction = PyObject_CallFunction(pkgcore_depset_PkgCond,
        "sOO", "use", val, payload);
    Py_DECREF(val);
    return restriction;
}

#define SKIP_SPACES(ptr)     \
while ('\t' == *(ptr) || ' ' == *(ptr) || '\n' == *(ptr)) (ptr)++;

#define SKIP_NONSPACES(ptr)                                                  \
while('\t' != *(ptr) && ' ' != *(ptr) && '\n' != *(ptr) && '\0' != *(ptr))  \
    (ptr)++;

#define ISSPACE(ptr) ('\t' == *(ptr) || ' ' == *(ptr) || '\n' == *(ptr))

static PyObject *
internal_parse_depset(PyObject *dep_str, char **ptr, int *has_conditionals,
    PyObject *element_func,
    PyObject *and_func, PyObject *or_func,
    PyObject *parent_func,
    char initial_frame)
{
    char *start = *ptr;
    char *p = NULL;
    PyObject *restrictions = NULL;
    PyObject *item = NULL;
    PyObject *tmp = NULL;
    PyObject *kwds = NULL;

    // should just use alloca here.

    #define PARSE_DEPSET_STACK_STORAGE 16
    PyObject *stack_restricts[PARSE_DEPSET_STACK_STORAGE];
    Py_ssize_t item_count = 0, tup_size = PARSE_DEPSET_STACK_STORAGE;
    Py_ssize_t item_size = 1;

    SKIP_SPACES(start);
    p = start;
    while('\0' != *start) {
        start = p;
        SKIP_NONSPACES(p);
        if('(' == *start) {
            // new and frame.
            if(!and_func) {
                Err_SetParse(dep_str, "this depset doesn't support and blocks",
                start, p);
                goto internal_parse_depset_error;
            }
            if(p - start != 1) {
                Err_SetParse(dep_str,
                    "either a space or end of string is required after (",
                    start, p);
                goto internal_parse_depset_error;
            }
            if(!(tmp = internal_parse_depset(dep_str, &p, has_conditionals,
                element_func, and_func, or_func, and_func, 0)))
                goto internal_parse_depset_error;

            if(tmp == Py_None) {
                Py_DECREF(tmp);
                Err_SetParse(dep_str, "empty payload", start, p);
                goto internal_parse_depset_error;
            } else if(!PyTuple_CheckExact(tmp)) {
                item = tmp;
            } else if (parent_func && and_func == parent_func) {
                item = tmp;
                item_size = PyTuple_GET_SIZE(item);
            } else {
                if(!(kwds = Py_BuildValue("{sO}", "finalize", Py_True))) {
                    Py_DECREF(tmp);
                    goto internal_parse_depset_error;
                }

                item = PyObject_Call(and_func, tmp, kwds);
                Py_DECREF(kwds);
                Py_DECREF(tmp);
                if(!item)
                    goto internal_parse_depset_error;
            }

        } else if(')' == *start) {
            // end of a frame
            if(initial_frame) {
                Err_SetParse(dep_str, ") found without matching (",
                    NULL, NULL);
                goto internal_parse_depset_error;
            }
            if(p - start != 1) {
                Err_SetParse(dep_str,
                    "either a space or end of string is required after )",
                    start, p);
                goto internal_parse_depset_error;
            }

            if(!*p)
                p--;
            break;

        } else if('?' == p[-1]) {
            // use conditional
            if (p - start == 1 || ('!' == *start && p - start == 2)) {
                Err_SetParse(dep_str, "empty use conditional", start, p);
                goto internal_parse_depset_error;
            }
            char *conditional_end = p - 1;
            SKIP_SPACES(p);
            if ('(' != *p) {
                Err_SetParse(dep_str,
                    "( has to be the next token for a conditional",
                    start, p);
                goto internal_parse_depset_error;
            } else if(!ISSPACE(p + 1) || '\0' == p[1]) {
                Err_SetParse(dep_str,
                    "( has to be followed by whitespace",
                    start, p);
                goto internal_parse_depset_error;
            }
            p++;
            if(!(tmp = internal_parse_depset(dep_str, &p, has_conditionals,
                element_func, and_func, or_func, NULL, 0)))
                goto internal_parse_depset_error;

            if(tmp == Py_None) {
                Py_DECREF(tmp);
                Err_SetParse(dep_str, "empty payload", start, p);
                goto internal_parse_depset_error;

            } else if(!PyTuple_CheckExact(tmp)) {
                item = PyTuple_New(1);
                if(!tmp) {
                    Py_DECREF(item);
                    goto internal_parse_depset_error;
                }
                PyTuple_SET_ITEM(item, 0, tmp);
                tmp = item;
            }
            item = make_use_conditional(start, conditional_end, tmp);
            Py_DECREF(tmp);
            if(!item)
                goto internal_parse_depset_error;
            *has_conditionals = 1;

        } else if ('|' == *start) {
            if('|' != start[1] || !or_func) {
                Err_SetParse(dep_str,
                    "stray |, or this depset doesn't support or blocks",
                    NULL, NULL);
                goto internal_parse_depset_error;
            }

            if(p - start != 2) {
                Err_SetParse(dep_str, "|| must have space followed by a (",
                    start, p);
                goto internal_parse_depset_error;
            }
            SKIP_SPACES(p);
            if ('(' != *p || (!ISSPACE(p + 1) && '\0' != p[1])) {
                Err_SetParse(dep_str,
                    "( has to be the next token for a conditional",
                    start, p);
                goto internal_parse_depset_error;
            }
            p++;
            if(!(tmp = internal_parse_depset(dep_str, &p, has_conditionals,
                element_func, and_func, or_func, NULL, 0)))
                goto internal_parse_depset_error;

            if(tmp == Py_None) {
                Py_DECREF(tmp);
                Err_SetParse(dep_str, "empty payload", start, p);
                goto internal_parse_depset_error;
            } else if (!PyTuple_CheckExact(tmp)) {
                item = tmp;
            } else {
                if(!(kwds = Py_BuildValue("{sO}", "finalize", Py_True))) {
                    Py_DECREF(tmp);
                    goto internal_parse_depset_error;
                }
                item = PyObject_Call(or_func, tmp, kwds);
                Py_DECREF(kwds);
                Py_DECREF(tmp);
                if(!item)
                    goto internal_parse_depset_error;
            }
        } else {
            char *ptr_s = start;
            while (ptr_s < p) {
                if('|' == *ptr_s || ')' == *ptr_s || '(' == *ptr_s) {
                    Err_SetParse(dep_str,
                        "stray character detected in item", start ,p);
                    goto internal_parse_depset_error;
                }
                ptr_s++;
            }
            item = PyObject_CallFunction(element_func, "s#", start, p - start);
            if(!item) {
                Err_WrapException(dep_str, start, p);
                goto internal_parse_depset_error;
            }
            assert(!PyErr_Occurred());
        }

        // append it.
        if(item_count + item_size > tup_size) {
            while(tup_size < item_count + item_size)
                tup_size <<= 1;
            if(!restrictions) {
                // switch over.
                if(!(restrictions = PyTuple_New(tup_size))) {
                    Py_DECREF(item);
                    goto internal_parse_depset_error;
                }
                Py_ssize_t x = 0;
                for(; x < item_count; x++) {
                    PyTuple_SET_ITEM(restrictions, x,
                        stack_restricts[x]);
                }
            } else if(_PyTuple_Resize(&restrictions, tup_size)) {
                Py_DECREF(item);
                goto internal_parse_depset_error;
            }
            // now we're using restrictions.
        }
        if(restrictions) {
            if(item_size == 1) {
                PyTuple_SET_ITEM(restrictions, item_count++, item);
            } else {
                Py_ssize_t x = 0;
                for(; x < item_size; x++) {
                    Py_INCREF(PyTuple_GET_ITEM(item, x));
                    PyTuple_SET_ITEM(restrictions, item_count + x,
                        PyTuple_GET_ITEM(item, x));
                }
                item_count += x;
                item_size = 1;
                // we're done with the tuple, already stole the items from it.
                Py_DECREF(item);
            }
        } else {
            if(item_size == 1) {
                stack_restricts[item_count++] = item;
            } else {
                Py_ssize_t x = 0;
                for(;x < item_size; x++) {
                    Py_INCREF(PyTuple_GET_ITEM(item, x));
                    stack_restricts[item_count + x] = PyTuple_GET_ITEM(item, x);
                }
                item_count += item_size;
                item_size = 1;
                // we're done with the tuple, already stole the items from it.
                Py_DECREF(item);
            }
        }
        SKIP_SPACES(p);
        start = p;
    }

    if(initial_frame) {
        if(*p) {
            Err_SetParse(dep_str, "stray ')' encountered", start, p);
            goto internal_parse_depset_error;
        }
    } else {
        if('\0' == *p) {
            Err_SetParse(dep_str, "depset lacks closure", *ptr, p);
            goto internal_parse_depset_error;
        }
        p++;
    }

    if(!restrictions) {
        if(item_count == 0) {
            restrictions = Py_None;
            Py_INCREF(restrictions);
        } else if(item_count == 1) {
            restrictions = stack_restricts[0];
        } else {
            restrictions = PyTuple_New(item_count);
            if(!restrictions)
                goto internal_parse_depset_error;
            Py_ssize_t x =0;
            for(;x < item_count; x++) {
                PyTuple_SET_ITEM(restrictions, x,
                    stack_restricts[x]);
            }
        }
    } else if(item_count < tup_size) {
        if(_PyTuple_Resize(&restrictions, item_count))
            goto internal_parse_depset_error;
    }
    *ptr = p;
    return restrictions;

    internal_parse_depset_error:
    if(item_count) {
        if(!restrictions) {
            item_count--;
            while(item_count >= 0) {
                Py_DECREF(stack_restricts[item_count]);
                item_count--;
            }
        } else
            Py_DECREF(restrictions);
    }
    // dealloc.
    return NULL;
}

static PyObject *
pkgcore_parse_depset(PyObject *self, PyObject *args)
{
    PyObject *dep_str, *element_func;
    PyObject *and_func = NULL, *or_func = NULL;
    if(!PyArg_ParseTuple(args, "SO|OO", &dep_str, &element_func, &and_func,
        &or_func))
        return NULL;

    int has_conditionals = 0;

    if(and_func == Py_None)
        and_func = NULL;
    if(or_func == Py_None)
        or_func = NULL;

    char *p = PyString_AsString(dep_str);
    if(!p)
        return NULL;
    PyObject *ret = internal_parse_depset(dep_str, &p, &has_conditionals,
        element_func, and_func, or_func, and_func, 1);
    if(!ret)
        return NULL;
    if(!PyTuple_Check(ret)) {
        PyObject *tmp;
        if(ret == Py_None) {
            tmp = PyTuple_New(0);
        } else {
            tmp = PyTuple_New(1);
            PyTuple_SET_ITEM(tmp, 0, ret);
        }
        if(!tmp) {
            Py_DECREF(ret);
            return NULL;
        }
        ret = tmp;
    }
    PyObject *conditionals_bool = has_conditionals ? Py_True : Py_False;
    Py_INCREF(conditionals_bool);

    PyObject *final = PyTuple_New(2);
    if(!final) {
        Py_DECREF(ret);
        Py_DECREF(conditionals_bool);
        return NULL;
    }
    PyTuple_SET_ITEM(final, 0, conditionals_bool);
    PyTuple_SET_ITEM(final, 1, ret);
    return final;
}

static PyMethodDef pkgcore_depset_methods[] = {
    {"parse_depset", (PyCFunction)pkgcore_parse_depset, METH_VARARGS,
        "initialize a depset instance"},
    {NULL}
};


PyDoc_STRVAR(
    pkgcore_depset_documentation,
    "cpython depset parsing functionality");


static int
load_external_objects()
{
    PyObject *s, *m = NULL;
    #define LOAD_MODULE(module)         \
    s = PyString_FromString(module);    \
    if(!s)                              \
        return 1;                       \
    m = PyImport_Import(s);             \
    Py_DECREF(s);                       \
    if(!m)                              \
        return 1;

    if(!pkgcore_depset_ParseErrorExc) {
        LOAD_MODULE("pkgcore.ebuild.errors");
        pkgcore_depset_ParseErrorExc = PyObject_GetAttrString(m,
            "ParseError");
        Py_DECREF(m);
        if(!pkgcore_depset_ParseErrorExc) {
            return 1;
        }
    }
    if(!pkgcore_depset_ValContains) {
        LOAD_MODULE("pkgcore.restrictions.values");
        pkgcore_depset_ValContains = PyObject_GetAttrString(m,
            "ContainmentMatch");
        Py_DECREF(m);
        if(!pkgcore_depset_ValContains)
            return 1;
    }
    if(!pkgcore_depset_PkgCond) {
        LOAD_MODULE("pkgcore.restrictions.packages");
        pkgcore_depset_PkgCond = PyObject_GetAttrString(m,
            "Conditional");
        Py_DECREF(m);
        if(!pkgcore_depset_PkgCond)
            return 1;
    }

    if(!pkgcore_depset_PkgAnd || !pkgcore_depset_PkgOr) {
        LOAD_MODULE("pkgcore.restrictions.boolean");
    } else
        m = NULL;

    #undef LOAD_MODULE

    #define LOAD_ATTR(ptr, attr)                            \
    if(!(ptr)) {                                            \
        if(!((ptr) = PyObject_GetAttrString(m, (attr)))) {  \
            Py_DECREF(m);                                   \
            return 1;                                       \
        }                                                   \
    }
    LOAD_ATTR(pkgcore_depset_PkgAnd, "AndRestriction");
    LOAD_ATTR(pkgcore_depset_PkgOr, "OrRestriction");
    #undef LOAD_ATTR

    Py_CLEAR(m);
    return 0;
}


PyMODINIT_FUNC
init_depset()
{
    // first get the exceptions we use.
    if(load_external_objects())
        /* XXX this returns *before* we called Py_InitModule3, so it
         * triggers a SystemError. But if we initialize the module
         * first python code can get at uninitialized pointers through
         * our exported functions, which would be worse.
         */
         return;

    if (!Py_InitModule3("_depset", pkgcore_depset_methods,
                        pkgcore_depset_documentation))
        return;

    /* Success! */
}
