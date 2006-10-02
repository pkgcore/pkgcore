/*
 * Copyright: 2006 Brian Harring <ferringb@gmail.com>
 * License: GPL2
 *
 * C version of cpv class for speed.
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

#include <Python.h>
#include <structmember.h>
#include <string.h>

/* From heapy */
#include "../heapdef.h"

// dev-util/diffball-cvs.2006.0_alpha1_alpha2
// dev-util/diffball

#define ISDIGIT(c) ('0' <= (c) && '9' >= (c))
#define ISALPHA(c) (('a' <= (c) && 'z' >= (c)) || ('A' <= (c) && 'Z' >= (c)))
#define ISLOWER(c) ('a' <= (c) && 'z' >= (c))
#define ISALNUM(c) (ISALPHA(c) || ISDIGIT(c))

typedef enum { SUF_ALPHA=0, SUF_BETA, SUF_PRE, SUF_RC, SUF_NORM, SUF_P } 
    version_suffixes;
const char * const version_suffixes_str[] = \
    {"alpha", "beta", "pre", "rc", "", "p", NULL};

struct suffix_ver {
    const char *str;
    int str_len;
    long val;
};

struct suffix_ver pkgcore_ebuild_suffixes[] = {
    {"alpha", 5, 0},
    {"beta", 4, 1},
    {"pre", 3, 2},
    {"rc", 2, 3},
    // note we skipped 4.  4 is the default.
    {"p", 1, 5},
    {NULL, 0, 6},
};

static const unsigned long pkgcore_ebuild_default_suffixes[] = {4, 0};
#define PKGCORE_EBUILD_SUFFIX_DEFAULT_SUF 4
#define PKGCORE_EBUILD_SUFFIX_DEFAULT_VAL 0

typedef struct {
    PyObject_HEAD
    PyObject *category;
    PyObject *package;
    PyObject *key;
    PyObject *fullver;
    PyObject *version;
    PyObject *revision;
    unsigned long *suffixes;
    long hash_val;
    int cvs;
} pkgcore_cpv;

static PyObject *pkgcore_InvalidCPV_Exc = NULL;


static int
pkgcore_cpv_set_cpvstr(pkgcore_cpv *self, PyObject *v, void *closure)
{
    PyErr_SetString(PyExc_AttributeError, "cpvstr is immutable");
    return -1;
}

static PyObject *
pkgcore_cpv_get_cpvstr(pkgcore_cpv *self, void *closure)
{
    if (!self->category || !self->package) {
        Py_RETURN_NONE;
    }
    if (!self->fullver) {
        return PyString_FromFormat("%s/%s",
            PyString_AsString(self->category),
            PyString_AsString(self->package));
    }
    return PyString_FromFormat("%s/%s-%s",
        PyString_AsString(self->category),
        PyString_AsString(self->package),
        PyString_AsString(self->fullver));
}

#define PKGCORE_IMMUTABLE_ATTRIBUTE(getter, setter, name, attribute)    \
static int                                                              \
setter (pkgcore_cpv *self, PyObject *v, void *closure)                  \
{                                                                       \
    PyErr_SetString(PyExc_AttributeError, name" is immutable");         \
    return -1;                                                          \
};                                                                      \
                                                                        \
static PyObject *                           \
getter (pkgcore_cpv *self, void *closure)   \
{                                           \
    if (self->attribute == NULL) {          \
        Py_RETURN_NONE;                     \
    }                                       \
    Py_INCREF(self->attribute);             \
    return self->attribute;                 \
}

PKGCORE_IMMUTABLE_ATTRIBUTE(pkgcore_cpv_get_category, pkgcore_cpv_set_category,
    "category", category);
PKGCORE_IMMUTABLE_ATTRIBUTE(pkgcore_cpv_get_package,  pkgcore_cpv_set_package,
    "package", package);
PKGCORE_IMMUTABLE_ATTRIBUTE(pkgcore_cpv_get_fullver,  pkgcore_cpv_set_fullver,
    "fullver", fullver);
PKGCORE_IMMUTABLE_ATTRIBUTE(pkgcore_cpv_get_version,  pkgcore_cpv_set_version,
    "version", version);
PKGCORE_IMMUTABLE_ATTRIBUTE(pkgcore_cpv_get_revision, pkgcore_cpv_set_revision,
    "revision", revision);
PKGCORE_IMMUTABLE_ATTRIBUTE(pkgcore_cpv_get_key, pkgcore_cpv_set_key, "key",
    key);

#undef PKGCORE_IMMUTABLE_ATTRIBUTE


static PyGetSetDef pkgcore_cpv_getsetters[] = {
    {"cpvstr",   (getter)pkgcore_cpv_get_cpvstr,
        (setter)pkgcore_cpv_set_cpvstr,   "cpvstr", NULL},
    {"category", (getter)pkgcore_cpv_get_category,
        (setter)pkgcore_cpv_set_category, "category", NULL},
    {"package",  (getter)pkgcore_cpv_get_package,
        (setter)pkgcore_cpv_set_package,  "package", NULL},
    {"key",      (getter)pkgcore_cpv_get_key,
        (setter)pkgcore_cpv_set_key,      "key", NULL},
    {"fullver",  (getter)pkgcore_cpv_get_fullver,
        (setter)pkgcore_cpv_set_fullver,  "fullver", NULL},
    {"version",  (getter)pkgcore_cpv_get_version,
        (setter)pkgcore_cpv_set_version,  "version", NULL},
    {"revision", (getter)pkgcore_cpv_get_revision,
        (setter)pkgcore_cpv_set_revision, "revision", NULL},
    {NULL}
};

char *
pkgcore_cpv_parse_category(const char *start, int null_is_end)
{
    char *p = (char *)start;
    if(NULL == start)
        return NULL;
    if(!null_is_end) {
        char *end = NULL;
        /* first char must be alnum, after that it's opened up. */
        while('\0' != *p) {
            if(!ISALNUM(*p))
                return NULL;
            p++;
            while(ISALNUM(*p) || '+' == *p || '-' == *p || '.' == *p \
                || '_' == *p)
                p++;
            if('/' == *p) {
                end = p;
                p++;
                if('/' == *p)
                    return NULL;
            } else {
                break;
            }
        }
        if(end) {
            p = end;
        } else if (!end) {
            // no '/', must be '\0'
            if('\0' != *p)
                return NULL;
       }
    } else {
        for (;;) {
            if(!ISALNUM(*p))
                return NULL;
            p++;
            while('\0' != *p && (ISALNUM(*p) || '+' == *p || '-' == *p \
                || '.' == *p || '_' == *p))
                p++;
            if('/' == *p) {
                p++;
                if('/' == *p)
                    return NULL;
            } else if('\0' == *p)
                break;
            else
                return NULL;
        }
    }
    if(p == start)
       return NULL;
    return p;
}

char *
pkgcore_cpv_parse_package(const char *start)
{
    // yay- need to eat the pkg next
    // allowed [a-zA-Z0-9](?:[-_+a-zA-Z0-9]*?[+a-zA-Z0-9])??)
    // ver-  "(?:-(?P<fullver>(?P<version>(?:cvs\\.)?(?:\\d+)(?:\\.\\d+)*[a-z]?(?:_(p(?:re)?|beta|alpha|rc)\\d*)*)" +
    // "(?:-r(?P<revision>\\d+))?))?$")
    // note that pkg regex is non-greedy.
    char *p = (char *)start;
    char *ver_start;
    if(NULL == start)
        return NULL;
    start = p;
    p = strchr(start, '-');
    while(NULL != p) {
        ++p;
        ver_start = p;
        if('\0' == *p)
             return NULL;
        if(0 == strncmp(p, "cvs.", 4)) {
            // we've got it.
            break;
        }
        while(ISDIGIT(*p))
            p++;
        if(p == ver_start) {
            p = strchr(ver_start + 1, '-');
            continue;
        }
        if('\0' == *p)
            break;
           
        // ok.  so, either it's a period, _, or a *single* [a-z].
        if('\0' == *p || '.' == *p || '_' == *p || '-' == *p) {
            break;
        } else if(ISLOWER(*p)) {
            p++;
            if('\0' == *p || '.' == *p || '_' == *p || '-' == *p)
                break;
        }
        p = strchr(p, '-');
    }
    // do verification of pkg for *both* branches
    if (!p) {
        // no pkg detected, find end, verification happens outside
        // the block
        p = (char *)start;
        while('\0' != *p)
            p++;
        ver_start = p;
    }
    if('\0' != *ver_start)
        ver_start--;
    return ver_start;
}


int
pkgcore_cpv_parse_version(pkgcore_cpv *self, char *ver_start, 
    char **ver_end)
{
    // version parsing.
    // "(?:-(?P<fullver>(?P<version>(?:cvs\\.)?(?:\\d+)(?:\\.\\d+)*[a-z]?(?:_(p(?:re)?|beta|alpha|rc)\\d*)*)" +
    // "(?:-r(?P<revision>\\d+))?))?$")
    char *p = ver_start;

    // suffixes _have_ to have versions; do it now to avoid
    if('_' == *p)
        return 1;

    // grab cvs chunk
    if(0 == strncmp(ver_start, "cvs.", 4)) {
        self->cvs = 1;
        p += 4;
        if('\0' == *p)
            return 1;
    }
    // (\d+)(\.\d+)*[a-z]?
    for(;;) {
        while(ISDIGIT(*p))
            p++;
        // safe due to our checks from above, but just in case...
        if(ver_start == p || '.' == p[-1]) {
            return 1;
        }
        if(ISALPHA(*p)) {
            p++;
            if('\0' != *p && '_' != *p && '-' != *p)
                return 1;
            break;
        } else if('.' == *p) {
            p++;
        } else if('\0' == *p || '_' == *p || '-' == *p) {
            break;
        } else {
            return 1;
        }
    }
    if('_' == *p) {
        // suffixes.  yay.
        char *orig_p = (char *)p;
        unsigned int suffix_count = 0;
        unsigned int pos;
        unsigned new_long;
        struct suffix_ver *sv;
        do {
            suffix_count++;
            p = strchr(p + 1, '_');
        } while(NULL != p);
        
        // trailing is 0 0
        
        p = orig_p;
        self->suffixes = PyObject_Malloc(sizeof(long) * (suffix_count + 1) * 2);
        if(NULL == self->suffixes) {
            // wanker.
            PyErr_NoMemory();
            return -2;
        }
        suffix_count *= 2;
        for(pos = 0; pos < suffix_count; pos += 2) {
            p += 1; // skip the leading _
            if('\0' == *p)
                return 1;
            for(sv = pkgcore_ebuild_suffixes; NULL != sv->str; sv++) {
                if(0 == strncmp(p, sv->str, sv->str_len)) {
                    self->suffixes[pos] = sv->val;
                    p += sv->str_len;
                    new_long = 0;
                    while(ISDIGIT(*p)) {
                        new_long = (new_long * 10) + *p - '0';
                        p++;
                    }
                    if('\0' != *p && '_' != *p && '-'  != *p)
                        return 1;
                    self->suffixes[pos + 1] = new_long;
                    break;
                }
            }
            if(NULL == sv->str) {
                // that means it didn't find the suffix.
                return 1;
            }
        }
        self->suffixes[pos] = PKGCORE_EBUILD_SUFFIX_DEFAULT_SUF;
        self->suffixes[pos + 1] = PKGCORE_EBUILD_SUFFIX_DEFAULT_VAL;
    } else {
        self->suffixes = (unsigned long *)pkgcore_ebuild_default_suffixes;
    }
    *ver_end = p;
    return 0;
}


static int
pkgcore_cpv_init(pkgcore_cpv *self, PyObject *args, PyObject *kwds)
{
    int result = 0;
    char *ver_end = NULL;
    char *p = NULL, *s1 = NULL, *s2 = NULL;
    char *cpv_char = NULL;
    char *cpv_pos = NULL;
    PyObject *tmp = NULL, *tmp2 = NULL, *cpvstr = NULL, *category = NULL, 
        *package = NULL, *fullver = NULL;

    if(!PyArg_UnpackTuple(args, "CPV", 1, 3, &category, &package, &fullver))
        return -1;

    if(kwds && PyObject_IsTrue(kwds)) {
        PyErr_SetString(PyExc_TypeError,
            "cpv accepts either 1 arg (cpvstr), or 3 (category, package, "
            "version); all must be strings, and no keywords accepted");
        goto cleanup;
    }

    if(package) {
        if(!fullver || !PyString_CheckExact(category) || 
            !PyString_CheckExact(package) || !PyString_CheckExact(fullver)) {
            PyErr_SetString(PyExc_TypeError,
                "cpv accepts either 1 arg (cpvstr), or 3 (category, package, "
                "version); all must be strings");
            goto cleanup;
        }
    } else {
        if (!PyString_CheckExact(category)) {
            PyErr_SetString(PyExc_TypeError,
                "cpv accepts either 1 arg (cpvstr), or 3 (category, package, "
                "version); all must be strings");
            goto cleanup;
        }
        cpvstr = category;
        category = NULL;
    }

    self->hash_val = -1;

    if(!category) {
        cpv_char = PyString_AsString(cpvstr);
        cpv_pos = pkgcore_cpv_parse_category(cpv_char, 0);
        if(!cpv_pos || '/' != *cpv_pos)
            goto parse_error;
        category = PyString_FromStringAndSize(cpv_char, cpv_pos - cpv_char);
        if(!category)
            goto cleanup;
        cpv_pos++;

    } else {
        p = PyString_AsString(category);
        p = pkgcore_cpv_parse_category(p, 1);
        if(!p || '\0' != *p)
            goto parse_error;
        Py_INCREF(category);
    }
    tmp = self->category;
    self->category = category;
    Py_XDECREF(tmp);

    if(!package) {
        p = pkgcore_cpv_parse_package(cpv_pos);
        if(!p || ('\0' != *p && '-' != *p))
            goto parse_error;
        if(NULL == (package = PyString_FromStringAndSize(cpv_pos, p - cpv_pos)))
            goto cleanup;
        cpv_pos = p;
    } else {
        p = pkgcore_cpv_parse_package(PyString_AsString(package));
        if(!p || '\0' != *p)
            goto parse_error;
        Py_INCREF(package);
    }
    tmp = self->package;
    self->package = package;
    Py_XDECREF(tmp);

    // package verification
    s1 = PyString_AsString(self->package);
    if(!s1)
        goto parse_error;
    s2 = s1;
    if(!ISALNUM(*s2))
        goto parse_error;
    s2++;
    while (ISALNUM(*s2) || '_' == *s2 || '+' == *s2)
        s2++;
    while('-' == *s2) {
        s2++;
        if('\0' == *s2)
            goto parse_error;
        if(ISDIGIT(*s2)) {
            s2++;
            while(ISDIGIT(*s2))
                s2++;
            if(!ISALPHA(*s2) && '+' != *s2)
                goto parse_error;
            s2++;
            if(!ISALPHA(*s2) && '+' != *s2)
                goto parse_error;
            while(ISALNUM(*s2) || '+' == *s2 || '_' == *s2)
                s2++;
        } else if(ISALPHA(*s2) || '+' == *s2) {
            s2++;
            while(ISALNUM(*s2) || '+' == *s2 || '_' == *s2)
                s2++;
        } else {
            goto parse_error;
        }
    }
    if('\0' != *s2)
        goto parse_error;	

    if(!fullver) {
        if('\0' != *p)
            cpv_pos++;
        p = cpv_pos;
    } else {
        p = PyString_AsString(fullver);
        if(!p)
            goto cleanup;
    }
    if('\0' != *p) {
        result = pkgcore_cpv_parse_version(self, p, &ver_end);
        if(result < 0)
            goto cleanup;
        else if(result > 0)
            goto parse_error;
        // doesn't look right.
        if('\0' == *ver_end) {
            if(fullver) {
                // no rev; set version to fullver
                Py_INCREF(fullver);
            } else {
                if(NULL == 
                    (fullver = PyString_FromStringAndSize(cpv_pos, ver_end - p)))
                    goto cleanup;
            }
            tmp = self->version;
            self->version = fullver;
            Py_XDECREF(tmp);
            Py_CLEAR(self->revision);
            Py_INCREF(fullver);
        } else if('-' == *ver_end) {
            if(NULL == (tmp = PyString_FromStringAndSize(p, ver_end - p)))
                goto cleanup;
            tmp2 = self->version;
            self->version = tmp;
            Py_XDECREF(tmp2);
            unsigned long revision = 0;
            // ok, revision.
            p = ver_end;
            p++;
            if('r' != *p)
                goto parse_error;
            p++;
            while(ISDIGIT(*p)) {
                revision = (revision * 10) + *p - '0';
                p++;
            }
            if('\0' != *p || 'r' == p[-1])
                goto parse_error;
            tmp = PyInt_FromLong(revision);
            if(!tmp) {
                result = -1;
                goto cleanup;
            }
            tmp2 = self->revision;
            self->revision = tmp;
            Py_XDECREF(tmp2);
            if(!fullver) {
                if(NULL == (fullver = PyString_FromStringAndSize(cpv_pos,
                    p - cpv_pos)))
                    goto cleanup;
            } else {
                Py_INCREF(fullver);
            }
        } else {
            goto parse_error;
        }
        tmp = self->fullver;
        self->fullver = fullver;
        Py_XDECREF(tmp);
    } else {
        Py_CLEAR(self->fullver);
        Py_CLEAR(self->version);
        Py_CLEAR(self->revision);
    }


    // by now, category, package, version, revision, and fullver should
    // be initialized.  key, and cpvstr now.

    tmp = NULL;
    if(cpvstr) {
        self->hash_val = PyObject_Hash(cpvstr);
        if(self->hash_val == -1)
            goto cleanup;
        if(!self->fullver) {
            Py_INCREF(cpvstr);
            tmp = cpvstr;
        }
    }
    if(!tmp) {
        tmp = PyString_FromFormat("%s/%s", PyString_AsString(self->category),
            PyString_AsString(self->package));
        if(!tmp)
            goto cleanup;
    }
    tmp2 = self->key;
    self->key = tmp;
    Py_XDECREF(tmp2);
    return 0;

parse_error:
    // yay.  well, set an exception.
    // if an error from trying to call, let it propagate.  meanwhile, we
    // cleanup our own
    if(!cpvstr) {
        if(PySequence_Length(fullver) != 0) {
            cpvstr = PyString_FromFormat("%s/%s-%s", PyString_AsString(category),
                PyString_AsString(package), PyString_AsString(fullver));
        } else {
            cpvstr = PyString_FromFormat("%s/%s", PyString_AsString(category),
                PyString_AsString(package));
        }
        if(!cpvstr)
            goto cleanup;
    }
    tmp = PyObject_CallFunction(pkgcore_InvalidCPV_Exc, "O", cpvstr);
    if(NULL != tmp) {
        PyErr_SetObject(pkgcore_InvalidCPV_Exc, tmp);
        Py_DECREF(tmp);
    } 
cleanup:

    Py_CLEAR(self->category);
    Py_CLEAR(self->package);
    Py_CLEAR(self->key);
    Py_CLEAR(self->version);
    Py_CLEAR(self->revision);
    Py_CLEAR(self->fullver);

    if(NULL != self->suffixes) {
        // if we're not using the communal val...
        if(PKGCORE_EBUILD_SUFFIX_DEFAULT_SUF != self->suffixes[0]) {
            PyObject_Free(self->suffixes);
        }
        self->suffixes = NULL;
    }
    return -1;
}


static void
pkgcore_cpv_dealloc(pkgcore_cpv *self)
{
    Py_CLEAR(self->category);
    Py_CLEAR(self->package);
    Py_CLEAR(self->key);
    Py_CLEAR(self->version);
    Py_CLEAR(self->revision);
    Py_CLEAR(self->fullver);

    if(NULL != self->suffixes) {
        if(PKGCORE_EBUILD_SUFFIX_DEFAULT_SUF != self->suffixes[0]) {
            PyObject_Free(self->suffixes);
        }
        self->suffixes = NULL;
    }
    self->ob_type->tp_free((PyObject *)self);
}


static int
pkgcore_nullsafe_compare(PyObject *this, PyObject *other)
{
    if ((this == NULL || this == Py_None) &&
        (other == NULL || other == Py_None)) {
        return 0;
    }
    if (this == NULL || this == Py_None) {
        return -1;
    }
    if (other == NULL || other == Py_None) {
        return +1;
    }
    return PyObject_Compare(this, other);
}


static int
pkgcore_cpv_compare(pkgcore_cpv *self, pkgcore_cpv *other)
{
    int c;
    c = pkgcore_nullsafe_compare(self->category, other->category);
    if(PyErr_Occurred())
        return -1;
    if(c != 0)
        return c;
    c = pkgcore_nullsafe_compare(self->package, other->package);
    if(PyErr_Occurred())
        return -1;
    if(c != 0)
        return c;
    if(self->version == NULL)
        return other->version == NULL ? 0 : -1;
    
    if(self->cvs != other->cvs)
        return self->cvs ? +1 : -1;

    char *s1, *o1;
    s1 = PyString_AsString(self->version);
    if(!s1)
        return -1;
    o1 = PyString_AsString(other->version);
    if (!o1)
        return -1;

    if(self->cvs) {
        s1 += 4; // "cvs."
        o1 += 4;
    }
    while('_' != *s1 && '\0' != *s1 && '_' != *o1 && '\0' != *o1) {
        if('0' == *s1 || '0' == *o1) {
            // float comparison rules.
            do {
                if(*s1 > *o1)
                    return 1;
                else if (*s1 < *o1)
                    return -1;
                s1++; o1++;
            } while (ISDIGIT(*s1) && ISDIGIT(*o1));

            while(ISDIGIT(*s1)) {
                if('0' != *s1)
                    return +1;
                s1++;
            }
            while(ISDIGIT(*o1)) {
                if('0' != *o1)
                    return -1;
                o1++;
            }
        } else {
            // int comparison rules.
            char *s_start = s1, *o_start = o1;

            while(ISDIGIT(*s1))
                s1++;
            while(ISDIGIT(*o1))
                o1++;

            if((s1 - s_start) < (o1 - o_start))
                return -1;
            else if((s1 - s_start) > (o1 - o_start))
                return 1;
            
            char *s_end = s1;

            for(s1 = s_start, o1 = o_start; s1 != s_end; s1++, o1++) {
                if(*s1 < *o1)
                    return -1;
                else if (*s1 > *o1)
                    return 1;
            }
        }
        if(ISALPHA(*s1)) {
            if(ISALPHA(*o1)) {
                if(*s1 < *o1)
                    return -1;
                else if(*s1 > *o1)
                    return 1;
                o1++;
            } else 
                return 1;
            s1++;
        } else if ISALPHA(*o1) {
            return -1;
        }
        if('.' == *s1)
            s1++;
        if('.' == *o1)
            o1++;
        // hokay.  no resolution there.
    }
    // ok.  one of the two just ran out of vers; test on suffixes
    if(ISDIGIT(*s1)) {
        return +1;
    } else if(ISDIGIT(*o1)) {
        return -1;
    }
    // bugger.  exact same version string up to suffix pt.
    int x;
    for(x=0;;) {
        // cmp suffix type.
        if(self->suffixes[x] < other->suffixes[x])
            return -1;
        else if(self->suffixes[x] > other->suffixes[x])
            return +1;
        else if(PKGCORE_EBUILD_SUFFIX_DEFAULT_SUF == self->suffixes[x]) {
            // terminator.  one remaining element, but little point in testing
            // it.  to have hit here requires them to be the same also (for
            // those wondering why we're not testing)
            break;
        }
        x++;
        // cmp suffix val
        if(self->suffixes[x] < other->suffixes[x])
            return -1;
        else if(self->suffixes[x] > other->suffixes[x])
            return +1;
        x++;
    }
    // all that remains is revision.
    return pkgcore_nullsafe_compare(self->revision, other->revision);
}
    


static long
pkgcore_cpv_hash(pkgcore_cpv *self)
{
    if (self->hash_val == -1) {
        PyObject *s = PyObject_GetAttrString((PyObject *)self, "cpvstr");
        if(!s)
            return -1;
        self->hash_val = PyObject_Hash(s);
        Py_DECREF(s);
    }
    return self->hash_val;
}


static PyObject *
pkgcore_cpv_str(pkgcore_cpv *self)
{
    PyObject *s = PyObject_GetAttrString((PyObject *)self, "cpvstr");
    if(!s)
        return (PyObject *)NULL;
    if(s != Py_None) {
        return s;
    }
    PyObject *s2 = PyObject_Str(s);
    Py_DECREF(s);
    return s2;
}


static PyObject *
pkgcore_cpv_repr(pkgcore_cpv *self)
{
    PyObject *s, *cpv;
    cpv = PyObject_GetAttrString((PyObject *)self, "cpvstr");
    if(!cpv)
        return (PyObject *)NULL;
    s = PyObject_Repr(cpv);
    Py_DECREF(cpv);
    if(!s)
        return (PyObject *)NULL;
    char *str = PyString_AsString(s);
    if(!s) {
        Py_DECREF(s);
        return (PyObject *)NULL;
    }
    PyObject *s2 = PyString_FromFormat("CPV(%s)", str);
    Py_DECREF(s);
    return s2;
}
        
static PyTypeObject pkgcore_cpvType = {
    PyObject_HEAD_INIT(NULL)
    0,                                /* ob_size */
    "CPV",
    sizeof(pkgcore_cpv),              /* tp_basicsize */
    0,				  /* tp_itemsize */
    (destructor)pkgcore_cpv_dealloc,  /* tp_dealloc */
    0,                                /* tp_print */
    0,                                /* tp_getattr */
    0,                                /* tp_setattr */
    (cmpfunc)pkgcore_cpv_compare,     /* tp_compare */
    (reprfunc)pkgcore_cpv_repr,       /* tp_repr */
    0,                                /* tp_as_number */
    0,                                /* tp_as_sequence */
    0,                                /* tp_as_mapping */
    (hashfunc)pkgcore_cpv_hash,       /* tp_hash */
    0,                                /* tp_call */
    (reprfunc)pkgcore_cpv_str,        /* tp_str */
    0,                                /* tp_getattro */
    0,                                /* tp_setattro */
    0,                                /* tp_as_buffer */
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE, /* tp_flags */
    0,                                /* tp_doc */
    0,                                /* tp_traverse */
    0,                                /* tp_clear */
    0,                                /* tp_richcompare */
    0,                                /* tp_weaklistoffset */
    0,                                /* tp_iter */
    0,                                /* tp_iternext */
    0,                                /* tp_methods */
    0,                                /* tp_members */
    pkgcore_cpv_getsetters,           /* tp_getset */
    0,                                /* tp_base */
    0,                                /* tp_dict */
    0,                                /* tp_descr_get */
    0,                                /* tp_descr_set */
    0,                                /* tp_dictoffset */
    (initproc)pkgcore_cpv_init,       /* tp_init */
    0,                                /* tp_alloc */
    PyType_GenericNew,                /* tp_new */
};

PyDoc_STRVAR(
    pkgcore_cpv_documentation,
    "C reimplementation of pkgcore.ebuild.cpv.");

/* Copied from stdtypes.c in guppy */
#define VISIT(SLOT) \
    if (SLOT) { \
        err = visit((PyObject *)(SLOT), arg); \
        if (err) \
            return err; \
    }

#define ATTR(name) \
    if ((PyObject *)v->name == r->tgt &&                                \
        (r->visit(NYHR_ATTRIBUTE, PyString_FromString(#name), r)))      \
        return 1;

static int
pkgcore_cpv_heapytraverse(NyHeapTraverse* traverse)
{
    pkgcore_cpv *cpv = (pkgcore_cpv*)traverse->obj;
    void *arg = traverse->arg;
    visitproc visit = traverse->visit;
    int err;
    VISIT(cpv->category);
    VISIT(cpv->package);
    VISIT(cpv->key);
    VISIT(cpv->fullver);
    VISIT(cpv->version);
    VISIT(cpv->revision);
    return 0;
}

static int
pkgcore_cpv_heapyrelate(NyHeapRelate *r)
{
    pkgcore_cpv *v = (pkgcore_cpv*)r->src;
    ATTR(category);
    ATTR(package);
    ATTR(key);
    ATTR(fullver);
    ATTR(version);
    ATTR(revision);
    return 0;
}

static NyHeapDef pkgcore_cpv_heapdefs[] = {
    {
        0,                            /* flags */
        &pkgcore_cpvType,             /* type */
        0,                            /* size */
        pkgcore_cpv_heapytraverse,    /* traverse */
        pkgcore_cpv_heapyrelate       /* relate */
    },
    {0}
};


#ifndef PyMODINIT_FUNC	/* declarations for DLL import/export */
#define PyMODINIT_FUNC void
#endif
PyMODINIT_FUNC
init_cpv(void)
{
    PyObject *m, *s;

    // this may be redundant; do this so __builtins__["__import__"] is used.
    s = PyString_FromString("pkgcore.ebuild.cpv_errors");
    if(NULL == s)
        return;
    m = PyImport_Import(s);
    if(NULL == m)
        return;
    Py_DECREF(s);
    pkgcore_InvalidCPV_Exc = PyObject_GetAttrString(m, "InvalidCPV");
    if(NULL == pkgcore_InvalidCPV_Exc)
        return;
    pkgcore_cpvType.ob_type = &PyType_Type;

    if(PyType_Ready(&pkgcore_cpvType) < 0)
        return;
    m = Py_InitModule3("_cpv", NULL, pkgcore_cpv_documentation);

    if (NULL == m)
        return;

    Py_INCREF(&pkgcore_cpvType);
    PyModule_AddObject(m, "CPV", (PyObject *)&pkgcore_cpvType);
    PyObject *cobject = PyCObject_FromVoidPtrAndDesc(&pkgcore_cpv_heapdefs,
                                                     "NyHeapDef[] v1.0",
                                                     0);
    /* XXX this error handling here is messed up */
    if (cobject) {
        PyModule_AddObject(m, "_NyHeapDefs_", cobject);
    }
}
