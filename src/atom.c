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

// exceptions, loaded during initialization.
static PyObject *pkgcore_atom_MalformedAtom_Exc = NULL;
static PyObject *pkgcore_atom_InvalidCPV_Exc = NULL;

// restricts.
static PyObject *pkgcore_atom_VersionMatch = NULL;
static PyObject *pkgcore_atom_PackageRestrict = NULL;
static PyObject *pkgcore_atom_StrExactMatch = NULL;
static PyObject *pkgcore_atom_StrGlobMatch = NULL;
static PyObject *pkgcore_atom_ContainmentMatch = NULL;
static PyObject *pkgcore_atom_ValOr = NULL;
static PyObject *pkgcore_atom_ValAnd = NULL;

// ops.
static PyObject *pkgcore_atom_op_gt = NULL;
static PyObject *pkgcore_atom_op_ge = NULL;
static PyObject *pkgcore_atom_op_lt = NULL;
static PyObject *pkgcore_atom_op_le = NULL;
static PyObject *pkgcore_atom_op_eq = NULL;
static PyObject *pkgcore_atom_op_droprev = NULL;
static PyObject *pkgcore_atom_op_none = NULL;
static PyObject *pkgcore_atom_op_glob = NULL;
static PyObject *pkgcore_atom_cpv_parse = NULL;
// every attr it sets...
static PyObject *pkgcore_atom_cpvstr = NULL;
static PyObject *pkgcore_atom_key = NULL;
static PyObject *pkgcore_atom_category = NULL;
static PyObject *pkgcore_atom_package = NULL;
static PyObject *pkgcore_atom_version = NULL;
static PyObject *pkgcore_atom_revision = NULL;
static PyObject *pkgcore_atom_fullver = NULL;
static PyObject *pkgcore_atom_hash = NULL;
static PyObject *pkgcore_atom_use = NULL;
static PyObject *pkgcore_atom_slot = NULL;
static PyObject *pkgcore_atom_repo_id = NULL;
static PyObject *pkgcore_atom_restrict_repo_id = NULL;
static PyObject *pkgcore_atom_blocks = NULL;
static PyObject *pkgcore_atom_op = NULL;
static PyObject *pkgcore_atom_negate_vers = NULL;
static PyObject *pkgcore_atom_restrictions = NULL;

#define ISDIGIT(c) ('0' <= (c) && '9' >= (c))
#define ISALPHA(c) (('a' <= (c) && 'z' >= (c)) || ('A' <= (c) && 'Z' >= (c)))
#define ISLOWER(c) ('a' <= (c) && 'z' >= (c))
#define ISALNUM(c) (ISALPHA(c) || ISDIGIT(c))

#define VALID_USE_CHAR(c) (ISALNUM(c) || '-' == (c) \
    || '_' == (c) || '.' == (c) || '+' == (c))

static void
Err_SetMalformedAtom(PyObject *atom_str, char *raw_msg)
{
    PyObject *msg = PyString_FromString(raw_msg);
    if(!msg)
        return;
    PyObject *err = PyObject_CallFunction(pkgcore_atom_MalformedAtom_Exc,
        "OO", atom_str, msg);
    Py_DECREF(msg);
    if(err) {
        PyErr_SetObject(pkgcore_atom_MalformedAtom_Exc, err);
        Py_DECREF(err);
    }
}

static int
parse_use_deps(PyObject *atom_str, char **p_ptr, PyObject **use_ptr)
{
    char *p = *p_ptr;
    char *start = p;
    Py_ssize_t len = 1;
    PyObject *use = NULL;
    while('\0' != *p && ']' != *p) {
        if (',' == *p)
            len++;
        else if(!VALID_USE_CHAR(*p)) {
            Err_SetMalformedAtom(atom_str,
                "invalid char in use dep; each flag must be a-Z0-9_.-+");
            goto cleanup_use_processing;
        }
        p++;
    }
    char *end = p;
    if(len == 1)
        use = PyTuple_New(len);
    else
        use = PyList_New(len);
    if(!use)
        return 1;
    Py_ssize_t idx = 0;
    PyObject *s;
    p = len > 1 ? start : p;
    while(end != p) {
        if(',' == *p) {
            // flag...
            if(start == p) {
                Err_SetMalformedAtom(atom_str, 
                    "invalid use flag; must be non empty");
                goto cleanup_use_processing;
            } else if('-' == start[1] && start + 1 == p) {
                Err_SetMalformedAtom(atom_str,
                    "invalid use flag; must be non empty, got just a negation");
                goto cleanup_use_processing;
            }
            s = PyString_FromStringAndSize(start, p - start);
            if(!s)
                goto cleanup_use_processing;
            // steals the ref.
            if(PyList_SetItem(use, idx, s))
                goto cleanup_use_processing;
            idx++;
            start = p + 1;
        }
        p++;
    }
    // one more to add...
    if(start == p) {
        Err_SetMalformedAtom(atom_str,
            "invalid use flag; must be non empty");
        goto cleanup_use_processing;
    } else if('-' == start[1] && start + 1 == p) {
        Err_SetMalformedAtom(atom_str,
            "invalid use flag; must be non empty, got just a negation");
        goto cleanup_use_processing;
    }
    s = PyString_FromStringAndSize(start, end - start);
    if(!s) {
        goto cleanup_use_processing;
    } else {
        if(len == 1)
            PyTuple_SET_ITEM(use, idx, s);
        else if (PyList_SetItem(use, idx, s)) {
            goto cleanup_use_processing;
        }
    }
    if(len > 1) {
        // weak...
        if(PyList_Sort(use) < 0)
            goto cleanup_use_processing;
        PyObject *t = PyTuple_New(len);
        if(!t)
            goto cleanup_use_processing;
        register PyObject *x;
        for(idx=0; idx < len; idx++) {
            x = PyList_GET_ITEM(use, idx);
            Py_INCREF(x);
            PyTuple_SET_ITEM(t, idx, x);
        }
        Py_DECREF(use);
        use = t;
    }
    *use_ptr = use;
    *p_ptr = p + 1;
    return 0;
    cleanup_use_processing:
    Py_CLEAR(use);
    return 1;
}

static int
parse_slot_deps(PyObject *atom_str, char **p_ptr, PyObject **slots_ptr)
{
    char *p = *p_ptr;
    char *start = p;
    Py_ssize_t len = 1;
    PyObject *slots = NULL;
    while('\0' != *p && ':' != *p && '[' != *p) {
        if (',' == *p)
            len++;
        else if(!VALID_USE_CHAR(*p)) {
            Err_SetMalformedAtom(atom_str,
                "invalid char in slot dep; each flag must be a-Z0-9_.-+");
            goto cleanup_slot_processing;
        }
        p++;
    }
    char *end = p;
    if(NULL == (slots = PyTuple_New(len)))
        return 1;

    Py_ssize_t idx = 0;
    PyObject *s;
    p = len > 1 ? start : p;
    while(end != p) {
        if(',' == *p) {
            // flag...
            if(start == p) {
                Err_SetMalformedAtom(atom_str, 
                    "invalid slot dep; all slots must be non empty");
                goto cleanup_slot_processing;
            }
            s = PyString_FromStringAndSize(start, p - start);
            if(!s)
                goto cleanup_slot_processing;
            PyTuple_SET_ITEM(slots, idx, s);
            idx++;
            start = p + 1;
        }
        p++;
    }
    // one more to add...
    if(start == p) {
        Err_SetMalformedAtom(atom_str,
            "invalid slot flag; all slots must be non empty");
        goto cleanup_slot_processing;
    }
    s = PyString_FromStringAndSize(start, end - start);
    if(s) {
        PyTuple_SET_ITEM(slots, idx, s);
        *slots_ptr = slots;
        *p_ptr = p;
        return 0;
    }
    cleanup_slot_processing:
    Py_CLEAR(slots);
    return 1;
}

static int
parse_repo_id(PyObject *atom_str, char *p, PyObject **repo_id)
{
    char *start = p;
    while('\0' != *p) {
        if(!VALID_USE_CHAR(*p) && '/' != *p) {
            Err_SetMalformedAtom(atom_str,
                "invalid character in repo_id: "
                "valid characters are [a-Z0-9_.-+/]");
            return 1;
        }
        p++;
    }
 
    if(start == p) {
        Err_SetMalformedAtom(atom_str,
            "repo_id must not be empty");
        return 1;
    }
    *repo_id = PyString_FromStringAndSize(start, p - start);
    return *repo_id ? 0 : 1;
}

static int
parse_cpv(PyObject *atom_str, PyObject *cpv_str, PyObject *self,
    int *has_version)
{
    PyObject *tmp;
    PyObject *cpv = PyObject_CallFunction(pkgcore_atom_cpv_parse,
        "O", cpv_str);
    if(!cpv) {
        PyObject *type, *tb;
        PyErr_Fetch(&type, &tmp, &tb);
        PyObject *res = PyObject_CallFunction(type, "O", tmp);
        Py_XDECREF(tmp);
        Py_XDECREF(type);
        Py_XDECREF(tb);
        if(!res)
            return 1;
        tmp = PyObject_Str(res);
        if(!tmp)
            return 1;
        Py_DECREF(res);
        Err_SetMalformedAtom(atom_str, PyString_AsString(tmp));
        Py_DECREF(tmp);
        return 1;
    }

    #define STORE_ATTR(attr_name)                                   \
        if(NULL == (tmp = PyObject_GetAttr(cpv, attr_name))){ \
            goto parse_cpv_error;                                   \
        }                                                           \
        if(PyObject_GenericSetAttr(self, attr_name, tmp)) {          \
            Py_DECREF(tmp);                                         \
            goto parse_cpv_error;                                   \
        }                                                           \
        Py_DECREF(tmp);
        
    STORE_ATTR(pkgcore_atom_cpvstr);
    STORE_ATTR(pkgcore_atom_category);
    STORE_ATTR(pkgcore_atom_package);
    STORE_ATTR(pkgcore_atom_key);
    tmp = PyObject_GetAttr(cpv, pkgcore_atom_fullver);
    if(!tmp)
        goto parse_cpv_error;
    *has_version = PyObject_IsTrue(tmp);
    if(PyErr_Occurred()) {
        Py_DECREF(tmp);
        goto parse_cpv_error;
    }
    if(PyObject_GenericSetAttr(self, pkgcore_atom_fullver, tmp)) {
        Py_DECREF(tmp);
        goto parse_cpv_error;
    }
    Py_DECREF(tmp);
    if(*has_version) {
        STORE_ATTR(pkgcore_atom_version);
        STORE_ATTR(pkgcore_atom_revision);
    } else {
        if(PyObject_GenericSetAttr(self, pkgcore_atom_version, Py_None))
            goto parse_cpv_error;
        if(PyObject_GenericSetAttr(self, pkgcore_atom_revision, Py_None))
            goto parse_cpv_error;
    }        
    
    #undef STORE_ATTR
    Py_DECREF(cpv);
    return 0;

    parse_cpv_error:
    Py_DECREF(cpv);
    return 1;
}

static PyObject *
pkgcore_atom_init(PyObject *self, PyObject *args, PyObject *kwds)
{
    PyObject *atom_str, *negate_vers = NULL;
    static char *kwlist[] = {"atom_str", "negate_vers", NULL};
    if(!PyArg_ParseTupleAndKeywords(args, kwds, "S|O:atom_init", kwlist,
        &atom_str, &negate_vers))
        return (PyObject *)NULL;
    
    if(!negate_vers) {
        negate_vers = Py_False;
    } else {
        int ret = PyObject_IsTrue(negate_vers);
        if (ret == -1)
            return NULL;
        negate_vers = ret ? Py_True : Py_False;
    }        
    Py_INCREF(negate_vers);
    char blocks = 0;
    char *p, *atom_start;
    atom_start = p = PyString_AsString(atom_str);

    if('!' == *p) {
        blocks++;
        p++;
    }
    
    // handle op...
    
    PyObject *op = pkgcore_atom_op_none;
    if('<' == *p) {
        if('=' == p[1]) {
            op = pkgcore_atom_op_le;
            p += 2;
        } else {
            op = pkgcore_atom_op_lt;
            p++;
        }
    } else if('>' == *p) {
        if('=' == p[1]) {
            op = pkgcore_atom_op_ge;
            p += 2;
        } else {
            op = pkgcore_atom_op_gt;
            p++;
        }
    } else if ('=' == *p) {
        op = pkgcore_atom_op_eq;
        p++;
    } else if ('~' == *p) {
        op = pkgcore_atom_op_droprev;
        p++;
    } else
        op = pkgcore_atom_op_none;

    Py_INCREF(op);

    // look for : or [
    atom_start = p;
    char *cpv_end = NULL;
    PyObject *slot = NULL, *use = NULL, *repo_id = NULL;
    while('\0' != *p) {
        if('[' == *p) {
            if(!cpv_end)
                cpv_end = p;
            if(use) {
                Err_SetMalformedAtom(atom_str,
                    "multiple use blocks aren't allowed");
                goto pkgcore_atom_parse_error;
            }
            p++;
            if(parse_use_deps(atom_str, &p, &use))
                goto pkgcore_atom_parse_error;
        } else if(':' == *p) {
            if(!cpv_end)
                cpv_end = p;
            p++;
            if(':' == *p) {
                // repo_id.
                p++;
                if(parse_repo_id(atom_str, p, &repo_id))
                    goto pkgcore_atom_parse_error;
                break;
            } else if(slot) {
                Err_SetMalformedAtom(atom_str,
                    "multiple slot blocks aren't allowed, use ',' to specify "
                    "multiple slots");
                goto pkgcore_atom_parse_error;
            } else if(parse_slot_deps(atom_str, &p, &slot)) {
                goto pkgcore_atom_parse_error;
            }
        } else if(cpv_end) {
            // char in between chunks...
            Err_SetMalformedAtom(atom_str,
                "interstitial characters between use/slot/repo_id blocks "
                "aren't allowed");
            goto pkgcore_atom_parse_error;
        } else {
            p++;
        }
    }
    
    PyObject *cpv_str = NULL;
    if(!cpv_end)
        cpv_end = p;
    if (!cpv_end && op == pkgcore_atom_op_none) {
        Py_INCREF(atom_str);
        cpv_str = atom_str;
    } else {
        if(op == pkgcore_atom_op_eq && atom_start + 1 < cpv_end && 
            '*' == cpv_end[-1]) {
            Py_DECREF(op);
            Py_INCREF(pkgcore_atom_op_glob);
            op = pkgcore_atom_op_glob;
            cpv_str = PyString_FromStringAndSize(atom_start,
                cpv_end - atom_start -1);
        } else {
            cpv_str = PyString_FromStringAndSize(atom_start, 
                cpv_end - atom_start);
        }
        if(!cpv_str)
            goto pkgcore_atom_parse_error;
    }
    int has_version;
    if(parse_cpv(atom_str, cpv_str, self, &has_version)) {
        Py_DECREF(cpv_str);
        goto pkgcore_atom_parse_error;
    }
    Py_DECREF(cpv_str);

    // ok... everythings parsed... sanity checks on the atom.
    if(op != pkgcore_atom_op_none) {
        if (!has_version) {
            Err_SetMalformedAtom(atom_str,
                "operator requires a version");
            goto pkgcore_atom_parse_error;
        }
    } else if(has_version) {
        Err_SetMalformedAtom(atom_str,
            "versioned atom requires an operator");
        goto pkgcore_atom_parse_error;
    }

    if(!use) {
        Py_INCREF(Py_None);
        use = Py_None;
    }
    if(!slot) {
        Py_INCREF(Py_None);
        slot = Py_None;
    }
    if(!repo_id) {
        Py_INCREF(Py_None);
        repo_id = Py_None;
    }

    // store remaining attributes...

    long hash_val = PyObject_Hash(atom_str);
    PyObject *tmp;
    if(hash_val == -1 || !(tmp = PyLong_FromLong(hash_val)))
        goto pkgcore_atom_parse_error;
    if(PyObject_GenericSetAttr(self, pkgcore_atom_hash, tmp)) {
        Py_DECREF(tmp);
        goto pkgcore_atom_parse_error;
    }
    Py_DECREF(tmp);

    #define STORE_ATTR(attr_name, val)              \
    if(PyObject_GenericSetAttr(self, (attr_name), (val)))  \
        goto pkgcore_atom_parse_error;

    STORE_ATTR(pkgcore_atom_blocks, blocks ? Py_True : Py_False);
    STORE_ATTR(pkgcore_atom_op, op);
    STORE_ATTR(pkgcore_atom_use, use);
    STORE_ATTR(pkgcore_atom_slot, slot);
    STORE_ATTR(pkgcore_atom_repo_id, repo_id);
    STORE_ATTR(pkgcore_atom_negate_vers, negate_vers);
    #undef STORE_ATTR

    Py_RETURN_NONE;

    pkgcore_atom_parse_error:
    Py_DECREF(op);
    Py_CLEAR(use);
    Py_CLEAR(slot);
    Py_CLEAR(repo_id);
    Py_CLEAR(negate_vers);
    return (PyObject *)NULL;
}

static inline PyObject *
make_simple_restrict(PyObject *attr, PyObject *str, PyObject *val_restrict)
{
    PyObject *tmp = PyObject_CallFunction(val_restrict, "O", str);
    if(tmp) {
        PyObject *tmp2 = PyObject_CallFunction(pkgcore_atom_PackageRestrict,
            "OO", attr, tmp);
        Py_DECREF(tmp);
        if(tmp2) {
            return tmp2;
        }
    }
    return NULL;
}

static inline int
make_version_kwds(PyObject *inst, PyObject **kwds)
{
    PyObject *negated = PyObject_GetAttr(inst, pkgcore_atom_negate_vers);
    if(!negated)
        return 1;
    if(negated != Py_False && negated != Py_None) {
        if(negated != Py_True) {
            int ret = PyObject_IsTrue(negated);
            Py_DECREF(negated);
            if(ret == -1)
                return 1;
            if(ret == 1) {
                Py_INCREF(Py_True);
                negated = Py_True;
            } else {
                negated = NULL;
            }
        }
        if(negated) {
            *kwds = PyDict_New();
            if(!*kwds) {
                Py_DECREF(negated);
                return 1;
            }
            if(PyDict_SetItemString(*kwds, "negate", negated)) {
                Py_DECREF(*kwds);
                Py_DECREF(negated);
                return 1;
            }
            Py_DECREF(negated);
        } else {
            *kwds = NULL;
        }
    } else {
        Py_DECREF(negated);
        *kwds = NULL;
    }
    return 0;
}

// handles complex version restricts, rather then glob matches
static inline PyObject *
make_version_restrict(PyObject *inst, PyObject *op)
{
    PyObject *ver = PyObject_GetAttr(inst, pkgcore_atom_version);
    if(ver) {
        PyObject *tup = PyTuple_New(3);
        if(!tup)
            return NULL;
        Py_INCREF(op);
        PyTuple_SET_ITEM(tup, 0, op);
        PyTuple_SET_ITEM(tup, 1, ver);
        PyObject *rev;
        if(op == pkgcore_atom_op_droprev) {
            Py_INCREF(Py_None);
            rev = Py_None;
        } else if(!(rev = PyObject_GetAttr(inst, pkgcore_atom_revision))) {
            Py_DECREF(tup);
            return NULL;
        }
        PyTuple_SET_ITEM(tup, 2, rev);
        PyObject *kwds = NULL;
        if(!make_version_kwds(inst, &kwds)) {
            // got our args, and kwds...
            PyObject *ret = PyObject_Call(pkgcore_atom_VersionMatch,
                tup, kwds);
            Py_DECREF(tup);
            Py_XDECREF(kwds);
            return ret;
        }
        // since we've been using SET_ITEM, and did _not_ incref op
        // (stole temporarily), we have to wipe it now for the decref.
        Py_DECREF(tup);
        // since tup steals, that just wiped ver, and rev.
    }
    return NULL;
}

static inline PyObject *
make_slot_restrict(PyObject *slot)
{
    PyObject *tup = PyTuple_New(PyTuple_GET_SIZE(slot));
    if(!tup)
        return NULL;

    // whee;  convert 'em, basically a map statement.
    // use args repeatedly to avoid allocation; the callee cannot modify it
    // (they can technically, but that's massively broken behavior).
    
    Py_ssize_t idx;
    for(idx=0; idx < PyTuple_GET_SIZE(slot); idx++) {
        PyObject *s = PyTuple_GET_ITEM(slot, idx);
        PyObject *tmp = PyObject_CallFunction(pkgcore_atom_StrExactMatch,
            "O", s);
        if(!tmp) {
            Py_DECREF(tup);
            return NULL;
        }
        PyTuple_SET_ITEM(tup, idx, tmp);
    }
    PyObject *tmp = PyObject_Call(pkgcore_atom_ValOr, tup, NULL);
    Py_DECREF(tup);
    if(tmp) {
        PyObject *tmp2 = PyObject_CallFunction(pkgcore_atom_PackageRestrict,
            "OO", pkgcore_atom_slot, tmp);
        Py_DECREF(tmp);
        tmp = tmp2;
    }
    return tmp;
}

static PyObject *
make_use_val_restrict(PyObject *use)
{
    if(!PyTuple_CheckExact(use)) {
        PyErr_SetString(PyExc_TypeError, "use must be None, or a tuple");
        return NULL;
    }
    // fun one.
    Py_ssize_t idx;
    Py_ssize_t false_len = 0;
    for(idx = 0; idx < PyTuple_GET_SIZE(use); idx++) {
        if(!PyString_CheckExact(PyTuple_GET_ITEM(use, idx))) {
            PyErr_SetString(PyExc_TypeError, "flags must be strings");
            return NULL;
        }
        if('-' == *PyString_AS_STRING(PyTuple_GET_ITEM(use, idx))) {
            false_len++;
        }
    }
    if(!false_len) {
        // easy case.
        if(PyTuple_GET_SIZE(use) == 1) {
            return PyObject_Call(pkgcore_atom_ContainmentMatch, use, NULL);
        }
        // slightly less easy.
        PyObject *kwds = Py_BuildValue("{sO}", "all", Py_True);
        if(kwds) {
            PyObject *ret = PyObject_Call(pkgcore_atom_ContainmentMatch, use,
                kwds);
            Py_DECREF(kwds);
            return ret;
        }
        return NULL;
    }
    // not so easy case.  need to split false use out, and make true use.

    PyObject *enabled = NULL;
    if(PyTuple_GET_SIZE(use) != false_len) {
        enabled = PyTuple_New(PyTuple_GET_SIZE(use) - false_len);
        if(!enabled)
            return NULL;
    }
    PyObject *disabled = PyTuple_New(false_len);
    if(!disabled) {
        Py_XDECREF(enabled);
        return NULL;
    }
    Py_ssize_t en_idx = 0, dis_idx = 0;
    for(idx = 0; idx < PyTuple_GET_SIZE(use); idx++) {
        PyObject *p = PyTuple_GET_ITEM(use, idx);
        if('-' == *PyString_AS_STRING(p)) {
            PyObject *s = PyString_FromStringAndSize(
                PyString_AS_STRING(p) + 1, PyString_GET_SIZE(p) - 1);
            if(!s) {
                Py_XDECREF(enabled);
                Py_DECREF(disabled);
                return NULL;
            }
            PyTuple_SET_ITEM(disabled, dis_idx, s);
            dis_idx++;
        } else {
            Py_INCREF(p);
            PyTuple_SET_ITEM(enabled, en_idx, p);
            en_idx++;
        }
    }
    PyObject *kwds = PyDict_New();
    if(kwds && (
        PyDict_SetItemString(kwds, "negate", Py_True) || 
        PyDict_SetItemString(kwds, "all", Py_True))) {
        Py_CLEAR(kwds);
    }
    if(!kwds) {
        // crappy.
        Py_XDECREF(enabled);
        Py_DECREF(disabled);
        return NULL;
    }
    PyObject *dis_val = PyObject_Call(pkgcore_atom_ContainmentMatch, disabled,
        kwds);
    Py_DECREF(kwds);
    Py_DECREF(disabled);
    if(!dis_val) {
        Py_DECREF(enabled);
        return NULL;
    }
    PyObject *tmp;
    if(enabled) {
        kwds = PyDict_New();
        if(kwds && PyDict_SetItemString(kwds, "all", Py_True)) {
            Py_CLEAR(kwds);
        }
        if(!kwds) {
            Py_DECREF(dis_val);
            Py_DECREF(enabled);
            return NULL;
        }

        PyObject *en_val = PyObject_Call(pkgcore_atom_ContainmentMatch,
            enabled, kwds);
        Py_DECREF(enabled);
        Py_DECREF(kwds);
        if(!en_val) {
            Py_DECREF(dis_val);
            return NULL;
        }
        tmp = PyObject_CallFunction(pkgcore_atom_ValAnd,
            "OO", dis_val, en_val);
        Py_DECREF(dis_val);
        Py_DECREF(en_val);
        if(!tmp) {
            return NULL;
        }
    } else {
        tmp = dis_val;
    }
    return tmp;
}

static PyObject *
pkgcore_atom_getattr(PyObject *getattr_inst, PyObject *args)
{
    int required = 2;
    int failed = 1;

    PyObject *self = NULL, *attr = NULL;
    if(!PyArg_ParseTuple(args, "OO", &self, &attr))
        return NULL;

    PyObject *op = NULL, *package = NULL, *category = NULL;
    PyObject *use = NULL, *slot = NULL, *repo_id = NULL;
    PyObject *tup = NULL, *tmp = NULL;

    // prefer Py_EQ since cpythons string optimizes that case.
    if(1 != PyObject_RichCompareBool(attr, pkgcore_atom_restrictions, Py_EQ)) {
        PyErr_SetObject(PyExc_AttributeError, attr);
        return NULL;
    }
    
    #define MUST_LOAD(ptr, str)                     \
    if(!((ptr) = PyObject_GetAttr(self, (str))))    \
        return NULL;
    
    MUST_LOAD(op, pkgcore_atom_op);
    MUST_LOAD(package, pkgcore_atom_package);
    MUST_LOAD(category, pkgcore_atom_category);    
    MUST_LOAD(use, pkgcore_atom_use);
    MUST_LOAD(slot, pkgcore_atom_slot);
    MUST_LOAD(repo_id, pkgcore_atom_repo_id);
    
    #undef MUST_LOAD

    if(op != pkgcore_atom_op_none)
        required++;
    if(use != Py_None)
        required++;    
    if(slot != Py_None)
        required++;
    if(repo_id != Py_None)
        required++;
    
    tup = PyTuple_New(required);
    if(!tup)
        goto pkgcore_atom_getattr_error;
    
    int idx = 0;
    if(repo_id != Py_None) {
        if(!(tmp = make_simple_restrict(pkgcore_atom_restrict_repo_id,
            repo_id, pkgcore_atom_StrExactMatch)))
            goto pkgcore_atom_getattr_error;
        PyTuple_SET_ITEM(tup, 0, tmp);
        idx++;
    }
    
    if(!(tmp = make_simple_restrict(pkgcore_atom_package, package,
        pkgcore_atom_StrExactMatch)))
        goto pkgcore_atom_getattr_error;
    PyTuple_SET_ITEM(tup, idx, tmp);
    idx++;
    
    if(!(tmp = make_simple_restrict(pkgcore_atom_category, category,
        pkgcore_atom_StrExactMatch)))
        goto pkgcore_atom_getattr_error;
    PyTuple_SET_ITEM(tup, idx, tmp);
    idx++;
    
    if(op != pkgcore_atom_op_none) {
        if(op == pkgcore_atom_op_glob) {
            PyObject *tmp2 = PyObject_GetAttr(self, pkgcore_atom_fullver);
            if(!tmp2) {
                goto pkgcore_atom_getattr_error;
            }
            tmp = make_simple_restrict(pkgcore_atom_fullver, tmp2,
                pkgcore_atom_StrGlobMatch);
            Py_DECREF(tmp2);
        } else {
            tmp = make_version_restrict(self, op);
        }
        if(!tmp)
            goto pkgcore_atom_getattr_error;
        PyTuple_SET_ITEM(tup, idx, tmp);
        idx++;
    }
    if(slot != Py_None) {
        tmp = NULL;
        if(!PyTuple_CheckExact(slot)) {
            PyErr_SetString(PyExc_TypeError, "slot must be tuple or None");
            goto pkgcore_atom_getattr_error;
        }
        if(PyTuple_GET_SIZE(slot) == 0) {
            if(_PyTuple_Resize(&tup, PyTuple_GET_SIZE(tup) - 1))
                goto pkgcore_atom_getattr_error;
        } else {
            if(1 == PyTuple_GET_SIZE(slot)) {
                tmp = make_simple_restrict(pkgcore_atom_slot, slot, 
                    pkgcore_atom_StrExactMatch);
            } else {
                tmp = make_slot_restrict(slot);
            }
            if(!tmp)
                goto pkgcore_atom_getattr_error;
            PyTuple_SET_ITEM(tup, idx, tmp);
        }
        idx++;
    }
    if(use != Py_None) {
        tmp = make_use_val_restrict(use);
        if(!tmp)
            goto pkgcore_atom_getattr_error;
        PyObject *tmp2 = PyObject_CallFunction(pkgcore_atom_PackageRestrict,
            "OO", pkgcore_atom_use, tmp);
        Py_DECREF(tmp);
        if(!tmp2)
            goto pkgcore_atom_getattr_error;
        PyTuple_SET_ITEM(tup, idx, tmp2);
        idx++;
    }
    failed = 0;
    pkgcore_atom_getattr_error:
    Py_XDECREF(op);
    Py_XDECREF(category);
    Py_XDECREF(package);
    Py_XDECREF(use);
    Py_XDECREF(slot);
    Py_XDECREF(repo_id);
    if(failed)
        Py_CLEAR(tup);
    else {
        if(PyObject_GenericSetAttr(self, pkgcore_atom_restrictions, tup)) {
            Py_CLEAR(tup);
        }
    }
    return tup;
}

PKGCORE_FUNC_BINDING("__init__", "pkgcore.ebuild._atom.__init__",
    pkgcore_atom_init, METH_VARARGS|METH_KEYWORDS)
PKGCORE_FUNC_BINDING("__getattr__", "pkgcore.ebuild._atom.__getattr__",
    pkgcore_atom_getattr, METH_O|METH_COEXIST)

PyDoc_STRVAR(
    pkgcore_atom_documentation,
    "cpython atom parsing functionality");

static int
load_external_objects()
{
    PyObject *s, *m = NULL;
    #define LOAD_MODULE(char_p)             \
    if(!(s = PyString_FromString(char_p)))  \
        return 1;                           \
    m = PyImport_Import(s);                 \
    Py_DECREF(s);                           \
    if(!m)                                  \
        return 1;
    
    if(!pkgcore_atom_MalformedAtom_Exc) {
        LOAD_MODULE("pkgcore.ebuild.errors");
        pkgcore_atom_MalformedAtom_Exc = PyObject_GetAttrString(m, 
            "MalformedAtom");
        Py_DECREF(m);
        if(!pkgcore_atom_MalformedAtom_Exc) {
            return 1;
        }
        m = NULL;
    }

    if(!pkgcore_atom_cpv_parse || !pkgcore_atom_InvalidCPV_Exc) {
        LOAD_MODULE("pkgcore.ebuild.cpv");
    }
    
    if(!pkgcore_atom_cpv_parse) {
        pkgcore_atom_cpv_parse = PyObject_GetAttrString(m, "base_CPV");
        if(!pkgcore_atom_cpv_parse)
            return 1;
    }
    if(!pkgcore_atom_InvalidCPV_Exc) {
        pkgcore_atom_InvalidCPV_Exc = PyObject_GetAttrString(m, "InvalidCPV");
        if(!pkgcore_atom_InvalidCPV_Exc)
            return 1;
    }
    if(m) {
        Py_DECREF(m);
    }
    
    if(!pkgcore_atom_VersionMatch) {
        LOAD_MODULE("pkgcore.ebuild.atom_restricts");
        pkgcore_atom_VersionMatch = PyObject_GetAttrString(m,
            "VersionMatch");
        Py_DECREF(m);
    }
    if(!pkgcore_atom_StrExactMatch || !pkgcore_atom_StrGlobMatch ||
        !pkgcore_atom_ContainmentMatch || !pkgcore_atom_ValAnd) {
        LOAD_MODULE("pkgcore.restrictions.values");
    } else
        m = NULL;
    
    #define LOAD_ATTR(ptr, name)                        \
    if(!(ptr) && !                                      \
        ((ptr) = PyObject_GetAttrString(m, (name)))) {  \
        Py_DECREF(m);                                   \
        return 1;                                       \
    }
    LOAD_ATTR(pkgcore_atom_StrExactMatch, "StrExactMatch");
    LOAD_ATTR(pkgcore_atom_StrGlobMatch, "StrGlobMatch");
    LOAD_ATTR(pkgcore_atom_ContainmentMatch, "ContainmentMatch");
    LOAD_ATTR(pkgcore_atom_ValAnd, "AndRestriction");
    LOAD_ATTR(pkgcore_atom_ValOr, "OrRestriction");
    if(m) {
        Py_DECREF(m);
    }
    if(!pkgcore_atom_PackageRestrict) {
        LOAD_MODULE("pkgcore.restrictions.packages");
        LOAD_ATTR(pkgcore_atom_PackageRestrict, "PackageRestriction");
        Py_DECREF(m);
    }
    #undef LOAD_ATTR
    #undef LOAD_MODULE
    return 0;
}


PyMODINIT_FUNC
init_atom()
{
    PyObject *m = Py_InitModule3("_atom", NULL, pkgcore_atom_documentation);
    if (!m)
        return;

    // first get the exceptions we use.
    if(load_external_objects())
        return;

    if(PyType_Ready(&pkgcore_atom_init_type) < 0)
        return;

    if(PyType_Ready(&pkgcore_atom_getattr_type) < 0)
        return;

    #define load_string(ptr, str)                   \
        if (!(ptr)) {                               \
            (ptr) = PyString_FromString(str);       \
            if(!(ptr))                              \
                return;                             \
        }

    load_string(pkgcore_atom_cpvstr,        "cpvstr");
    load_string(pkgcore_atom_key,           "key");
    load_string(pkgcore_atom_category,      "category");
    load_string(pkgcore_atom_package,       "package");
    load_string(pkgcore_atom_version,       "version");
    load_string(pkgcore_atom_revision,      "revision");
    load_string(pkgcore_atom_fullver,       "fullver");
    load_string(pkgcore_atom_hash,          "hash");
    load_string(pkgcore_atom_use,           "use");
    load_string(pkgcore_atom_slot,          "slot");
    load_string(pkgcore_atom_repo_id,       "repo_id");
    load_string(pkgcore_atom_restrict_repo_id,
                                            "repo.repo_id");
    load_string(pkgcore_atom_op_glob,       "=*");
    load_string(pkgcore_atom_blocks,        "blocks");
    load_string(pkgcore_atom_op,            "op");
    load_string(pkgcore_atom_negate_vers,   "negate_vers");
    load_string(pkgcore_atom_restrictions,  "restrictions");

    load_string(pkgcore_atom_op_ge,         ">=");
    load_string(pkgcore_atom_op_gt,         ">");
    load_string(pkgcore_atom_op_le,         "<=");
    load_string(pkgcore_atom_op_lt,         "<");
    load_string(pkgcore_atom_op_eq,         "=");
    load_string(pkgcore_atom_op_droprev,    "~");
    load_string(pkgcore_atom_op_none,       "");
    #undef load_string

    PyObject *d = PyDict_New();
    if(!d)
        return;

    PyObject *overrides = PyDict_New();
    if(!overrides)
        return;
    PyObject *tmp = PyType_GenericNew(&pkgcore_atom_init_type, NULL, NULL);
    if(!tmp)
        return;
    if(PyDict_SetItemString(overrides, "__init__", tmp))
        return;
    tmp = PyType_GenericNew(&pkgcore_atom_getattr_type, NULL, NULL);
    if(!tmp)
        return;
    if(PyDict_SetItemString(overrides, "__getattr__", tmp))
        return;
    PyModule_AddObject(m, "overrides", overrides);
    
    if (PyErr_Occurred()) {
        Py_FatalError("can't initialize module _atom");
    }
}
