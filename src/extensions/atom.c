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
static PyObject *pkgcore_atom_blocks = NULL;
static PyObject *pkgcore_atom_op = NULL;
static PyObject *pkgcore_atom_negate_vers = NULL;

#define ISDIGIT(c) ('0' <= (c) && '9' >= (c))
#define ISALPHA(c) (('a' <= (c) && 'z' >= (c)) || ('A' <= (c) && 'Z' >= (c)))
#define ISLOWER(c) ('a' <= (c) && 'z' >= (c))
#define ISALNUM(c) (ISALPHA(c) || ISDIGIT(c))

#define VALID_USE_CHAR(c) (ISALNUM(c) || '-' == (c) \
    || '_' == (c) || '.' == (c) || '+' == (c))

void
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

int
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
    use = PyTuple_New(len);
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
            PyTuple_SET_ITEM(use, idx, s);
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
    if(s) {
        PyTuple_SET_ITEM(use, idx, s);
        if(s) {
            *use_ptr = use;
            *p_ptr = p + 1;
            return 0;
        }
    }
    cleanup_use_processing:
    Py_CLEAR(use);
    return 1;
}

int
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

int
parse_repo_id(PyObject *atom_str, char *p, PyObject **repo_id)
{
    char *start = p;
    while('\0' != *p) {
        if(!VALID_USE_CHAR(*p)) {
            Err_SetMalformedAtom(atom_str,
                "invalid character in repo_id: "
                "valid characters are a-Z0-9_.-+");
            return 1;
        }
    }
 
    if(start == p) {
        Err_SetMalformedAtom(atom_str,
            "repo_id must not be empty");
        return 1;
    }
    *repo_id = PyString_FromStringAndSize(start, p - start);
    return *repo_id ? 0 : 1;
}

int
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
                if(!parse_repo_id(atom_str, p, &repo_id))
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


PKGCORE_FUNC_DESC("__init__", "pkgcore.ebuild._atom.__init__",
    pkgcore_atom_init, METH_VARARGS|METH_KEYWORDS);

PyDoc_STRVAR(
    pkgcore_atom_documentation,
    "cpython atom parsing functionality");

int
load_external_objects()
{
    PyObject *s, *m = NULL;
    if(!pkgcore_atom_MalformedAtom_Exc) {
        s = PyString_FromString("pkgcore.ebuild.errors");
        if(!s)
            return 1;
        m = PyImport_Import(s);
        Py_DECREF(s);
        if(!m)
            return 1;
        pkgcore_atom_MalformedAtom_Exc = PyObject_GetAttrString(m, 
            "MalformedAtom");
        Py_DECREF(m);
        if(!pkgcore_atom_MalformedAtom_Exc) {
            return 1;
        }
        m = NULL;
    }

    if(!pkgcore_atom_cpv_parse || !pkgcore_atom_InvalidCPV_Exc) {
        s = PyString_FromString("pkgcore.ebuild.cpv");
        if(!s)
            return 1;
        m = PyImport_Import(s);
        Py_DECREF(s);
        if(!m)
            return 1;
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
    return 0;
}


PyMODINIT_FUNC
init_atom()
{
    // first get the exceptions we use.
    if(load_external_objects())
        return;

    if(PyType_Ready(&pkgcore_atom_init_type) < 0)
        return;
    
    #define load_string(ptr, str)                   \
        if (!(ptr)) {                               \
            (ptr) = PyString_FromString(str);       \
            if(!(ptr))                              \
                return;                             \
        }

    load_string(pkgcore_atom_cpvstr,    "cpvstr");
    load_string(pkgcore_atom_key,       "key");
    load_string(pkgcore_atom_category,  "category");
    load_string(pkgcore_atom_package,   "package");
    load_string(pkgcore_atom_version,   "version");
    load_string(pkgcore_atom_revision,  "revision");
    load_string(pkgcore_atom_fullver,   "fullver");
    load_string(pkgcore_atom_hash,      "hash");
    load_string(pkgcore_atom_use,       "use");
    load_string(pkgcore_atom_slot,      "slot");
    load_string(pkgcore_atom_repo_id,   "repo_id");
    load_string(pkgcore_atom_op_glob,      "=*");
    load_string(pkgcore_atom_blocks,    "blocks");
    load_string(pkgcore_atom_op,        "op");
    load_string(pkgcore_atom_negate_vers,"negate_vers");

    load_string(pkgcore_atom_op_ge,         ">=");
    load_string(pkgcore_atom_op_gt,         ">");
    load_string(pkgcore_atom_op_le,         "<=");
    load_string(pkgcore_atom_op_lt,         "<");
    load_string(pkgcore_atom_op_eq,         "=");
    load_string(pkgcore_atom_op_droprev,    "~");
    load_string(pkgcore_atom_op_none,       "");
    #undef load_string
    
    PyObject *m = Py_InitModule3("_atom", NULL,
        pkgcore_atom_documentation);
    if(!m)
        return;
    PyObject *tmp = PyType_GenericNew(&pkgcore_atom_init_type, NULL, NULL);
    if(!tmp)
        return;
    PyModule_AddObject(m, "__init__", tmp);
    
    if (PyErr_Occurred()) {
        Py_FatalError("can't initialize module _atom");
    }
}
