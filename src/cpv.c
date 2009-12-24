/*
 * Copyright: 2006-2007 Brian Harring <ferringb@gmail.com>
 * License: GPL2/BSD
 *
 * C version of cpv class for speed.
 */

/* This does not really do anything since we do not use the "#"
 * specifier in a PyArg_Parse or similar call, but hey, not using it
 * means we are Py_ssize_t-clean too!
 */

#define PY_SSIZE_T_CLEAN

#include <snakeoil/common.h>
#include <structmember.h>
#include <string.h>


// dev-util/diffball-cvs.2006.0_alpha1_alpha2
// dev-util/diffball

// yes, it may seem whacked having these defined when 'isdigit' and friends
// already exist.  that said, they're a helluva lot slower in performance testing
// of it- presumably due to lack of inlining on a guess...

#define ISDIGIT(c) ('0' <= (c) && '9' >= (c))
#define ISALPHA(c) (('a' <= (c) && 'z' >= (c)) || ('A' <= (c) && 'Z' >= (c)))
#define ISLOWER(c) ('a' <= (c) && 'z' >= (c))
#define ISUPPER(c) ('A' <= (c) && 'Z' >= (c))
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

static struct suffix_ver pkgcore_ebuild_suffixes[] = {
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
        PyObject *tmp = self->key;
        Py_INCREF(tmp);
        return tmp;
    }
    return PyString_FromFormat("%s/%s-%s",
        PyString_AsString(self->category),
        PyString_AsString(self->package),
        PyString_AsString(self->fullver));
}


static PyGetSetDef pkgcore_cpv_getsetters[] = {
snakeoil_GETSET(pkgcore_cpv, "cpvstr", cpvstr),
    {NULL}
};

static PyMemberDef pkgcore_cpv_members[] = {
    {"category", T_OBJECT, offsetof(pkgcore_cpv, category), READONLY},
    {"package", T_OBJECT, offsetof(pkgcore_cpv, package), READONLY},
    {"key", T_OBJECT, offsetof(pkgcore_cpv, key), READONLY},
    {"fullver", T_OBJECT, offsetof(pkgcore_cpv, fullver), READONLY},
    {"version", T_OBJECT, offsetof(pkgcore_cpv, version), READONLY},
    {"revision", T_OBJECT, offsetof(pkgcore_cpv, revision), READONLY},
    {NULL}
};

static char *
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
        } else {
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

static int
pkgcore_cpv_valid_package(char *start, char *end)
{
    char *tok_start, *p;
    if(!end) {
        end = start;
        while('\0' != *end) {
            end++;
        }
    }
    tok_start = p = start;
    if(end == p)
        return 1;
    while(end != p) {
        while((ISALNUM(*p) || '_' == *p || '+' == *p) && end != p)
            p++;
        if(end == p)
            break;
        if('-' == *p) {
            // cannot have 'aa--f' nor 'aa-'
            p++;
            if(p == tok_start + 1 || p >= end) {
                return 1;
            }
        } else if ('\0' != *p) {
            return 1;
        } else {
            break;
        }
        tok_start = p;
    }
    // revalidate the last token to ensure it's not all digits
    p = tok_start;
    while(ISDIGIT(*p))
        p++;
    if(p == end)
        return 1;
    return 0;
}

static int
pkgcore_cpv_parse_version(pkgcore_cpv *self, char *ver_start,
    char *ver_end)
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
            return 2;
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
    if(p != ver_end)
        return 1;
    return 0;
}

static int
pkgcore_cpv_valid_revision(pkgcore_cpv *self, char *rev_start, char *rev_end)
{
    char *pos = rev_start;
    PyObject *revision = NULL, *tmp = NULL;

    if(rev_start == rev_end || rev_start +1 == rev_end)
        return 1;

    if('r' != *pos) {
        // not a revision; revision is store as NULL
        return 1;
    }
    pos++;
    unsigned long long revision_val = 0;
    while(pos != rev_end) {
        if(!ISDIGIT(*pos)) {
            // not a digit? invalid revision then.
            return 1;
        }
        revision_val = (revision_val * 10) + *pos - '0';
        pos++;
    }
    if(!revision_val) {
        Py_CLEAR(self->revision);
    } else {
        if(!(revision = PyLong_FromLongLong(revision_val))) {
            // XXX... this gets swallowed unfortunately due to the code flow.
            return 2;
        }
        tmp = self->revision;
        self->revision = revision;
        Py_XDECREF(tmp);
    }
    return 0;
}

static int
pkgcore_cpv_parse_from_components(pkgcore_cpv *self, PyObject *category,
    PyObject *package, PyObject *fullver, int versioned)
{
    PyObject *tmp = NULL, *tmp2 = NULL;
    int ret = 0;
    if(!pkgcore_cpv_parse_category(PyString_AsString(category), 1)) {
        return 1;
    }
    tmp = self->category;
    Py_INCREF(category);
    self->category = category;
    Py_XDECREF(tmp);
    if(0 != (ret = pkgcore_cpv_valid_package(PyString_AsString(package), NULL))) {
        return ret;
    }
    tmp = self->package;
    Py_INCREF(package);
    self->package = package;
    Py_XDECREF(tmp);
    if(versioned) {
        char *version_start = PyString_AsString(fullver);
        char *rev_start = version_start;
        char *version_end = NULL;

        while('\0' != *rev_start && '-' != *rev_start)
            rev_start++;
        version_end = rev_start;
        while('\0' != *version_end)
            version_end++;

        if(version_end == rev_start) {
            // no revision...
            Py_CLEAR(self->revision);
        } else {
            if(0 != (ret = pkgcore_cpv_valid_revision(self, rev_start + 1, version_end))) {
                return ret;
            }
        }

        if(0 != (ret = pkgcore_cpv_parse_version(self, version_start, rev_start))) {
            return ret; // either memory, or parse error.
        }

        if(rev_start == version_end) {
            // no revision;
            Py_INCREF(fullver);
            tmp = self->version;
            self->version = fullver;
            Py_XDECREF(tmp);
        } else {
            if(!(tmp = PyString_FromStringAndSize(version_start,
                rev_start - version_start))) {
                return 2;
            }
            tmp2 = self->version;
            self->version = tmp;
            Py_XDECREF(tmp2);
        }
        // bit of a hack. regardless of revision processing above, rely
        // on the stored revision value for deciding which to ref-
        // this is done to handle the case of -r0 being stripped
        tmp = self->revision ? fullver : self->version;
        Py_INCREF(tmp);
        tmp2 = self->fullver;
        self->fullver = tmp;
        Py_XDECREF(tmp2);

    } else {
        // unversioned
        Py_CLEAR(self->fullver);
        Py_CLEAR(self->version);
        Py_CLEAR(self->revision);
    }

    if(!(tmp = PyString_FromFormat("%s/%s", PyString_AsString(self->category),
        PyString_AsString(self->package)))) {
        return 2;
    }
    tmp2 = self->key;
    self->key = tmp;
    Py_XDECREF(tmp2);

    if(!versioned) {
        // we know that key is all that's needed... so hash it now.
        self->hash_val = PyObject_Hash(self->key);
        if(self->hash_val == -1) {
            return 2;
        }
    }

    return 0;
}

static int
pkgcore_cpv_parse_from_cpvstr(pkgcore_cpv *self, PyObject *cpvstr,
    int versioned)
{
    PyObject *tmp = NULL, *tmp2 = NULL;;
    char *pkg_start = NULL;
    char *cpv_pos = NULL;
    char *raw_cpvstr = PyString_AsString(cpvstr);
    char *cpv_end = raw_cpvstr;
    int ret = 0;

    while('\0' != *cpv_end) {
        cpv_end++;
    }

    pkg_start = pkgcore_cpv_parse_category(raw_cpvstr, 0);
    if(!pkg_start || '/' != *pkg_start) {
        return 1;
    }
    if(!(tmp = PyString_FromStringAndSize(raw_cpvstr, pkg_start - raw_cpvstr))) {
        return 2;
    }

    PyString_InternInPlace(&tmp);
    tmp2 = self->category;
    self->category = tmp;
    Py_CLEAR(tmp2);

    pkg_start++;

    if(versioned) {

        char *version_end = cpv_end;
        // try stripping off the revision.

        cpv_pos = version_end;
        while(cpv_pos > pkg_start && '-' != *cpv_pos)
            cpv_pos--;

        if(2 == (ret = pkgcore_cpv_valid_revision(self, cpv_pos + 1, cpv_end))) {
            // mem error...
            return ret;
        } else if (1 == ret) {
            // either there is no rev, or it's a bad rev.
            // check if it's a valid version.
            if(0 != (ret = pkgcore_cpv_parse_version(self, cpv_pos + 1, cpv_end))) {
                return ret; // either memory, or parse error.
            }
            // ok... no rev.
            Py_CLEAR(self->revision);
        } else {
            // revision exists, grab the next token for version
            version_end = cpv_pos;
            cpv_pos--;
            while(cpv_pos > pkg_start && '-' != *cpv_pos) {
                cpv_pos--;
            }
            if(cpv_pos == raw_cpvstr) {
                return 1;
            }
            if(0 != (ret = pkgcore_cpv_parse_version(self, cpv_pos + 1,
                version_end))) {
                // invalid version, or mem error.
                return ret;
            }
        }

        if(!(tmp = PyString_FromStringAndSize(cpv_pos + 1,
            version_end - (cpv_pos + 1)))) {
            return 2;
        }

        tmp2 = self->version;
        self->version = tmp;
        Py_CLEAR(tmp2);

        if(version_end == cpv_end || ! self->revision) {
            tmp = self->version;
            Py_INCREF(tmp);
        } else {
            if(!(tmp = PyString_FromString(cpv_pos +1))) {
                return 2;
            }
        }

        tmp2 = self->fullver;
        self->fullver = tmp;
        Py_XDECREF(tmp2);
        // version/rev/fullver handled.
    } else {
        // if not versioned, entire string must be a valid package name
        cpv_pos = cpv_end;
    }
    // validate package name finally.
    if(0 != (ret = pkgcore_cpv_valid_package(pkg_start, cpv_pos))) {
        return ret;
    }
    if(!(tmp = PyString_FromStringAndSize(pkg_start, cpv_pos - pkg_start))) {
        return 2;
    }
    PyString_InternInPlace(&tmp);
    tmp2 = self->package;
    self->package = tmp;
    Py_CLEAR(tmp2);

    if(versioned) {
        if(!(tmp = PyString_FromFormat("%s/%s", PyString_AsString(self->category),
            PyString_AsString(self->package)))) {
            return 2;
        }
    } else {
        if(-1 == (self->hash_val = PyObject_Hash(cpvstr)))
            return 2;
        tmp = cpvstr;
        Py_INCREF(tmp);
    }

    PyString_InternInPlace(&tmp);
    tmp2 = self->key;
    self->key = tmp;
    Py_XDECREF(tmp2);

    return 0;

}


static int
pkgcore_cpv_init(pkgcore_cpv *self, PyObject *args, PyObject *kwds)
{
    int result = 0;
    int versioned = 1;
    PyObject *category = NULL,  *package = NULL, *fullver = NULL, *cpvstr = NULL;

    if(!PyArg_UnpackTuple(args, "CPV", 1, 3, &category, &package, &fullver))
        return -1;

    if(!kwds) {
        versioned = -1;
    } else {
        Py_ssize_t len = PyObject_Length(kwds);
        if(len > 1) {
            PyErr_SetString(PyExc_TypeError,
                "cpv accepts only one keyword arguement- versioned");
            goto cleanup;
        } else if (len) {
            // borrowed ref.
            PyObject *versioned_obj = PyDict_GetItemString(kwds, "versioned");
            if(!versioned_obj) {
                PyErr_SetString(PyExc_TypeError,
                    "cpv only accepts a keyword of 'versioned'");
                goto cleanup;
            }
            if(-1 == (versioned = PyObject_IsTrue(versioned_obj))) {
                goto cleanup;
            }
        } else {
            if(!package) {
                PyErr_SetString(PyExc_TypeError,
                    "versioned keyword is required for single arg invocation");
                goto cleanup;
            }
        }
    }

    self->hash_val = -1;

    if(package) {
        if(!fullver || !PyString_CheckExact(category) ||
            !PyString_CheckExact(package) || !PyString_CheckExact(fullver)) {
            PyObject *err_msg = PyString_FromString(
                "cpv accepts either 1 arg (cpvstr), or 3 (category, package, "
                "version); all must be strings: got %r");
            if(err_msg) {
                PyObject *new_args = PyTuple_Pack(1, args);
                if(new_args) {
                    PyObject *s = PyString_Format(err_msg, new_args);
                    if(s) {
                        PyErr_SetString(PyExc_TypeError, PyString_AsString(s));
                        Py_CLEAR(s);
                    }
                    Py_CLEAR(new_args);
                }
                Py_CLEAR(err_msg);
            }
            goto cleanup;
        }
        result = pkgcore_cpv_parse_from_components(self, category, package,
            fullver, versioned);
    } else {
        if (!PyString_CheckExact(category)) {
            PyObject *err_msg = PyString_FromString(
                "cpv accepts either 1 arg (cpvstr), or 3 (category, package, "
                "version); all must be strings: got extra arg %r");
            if(err_msg) {
                PyObject *new_args = PyTuple_Pack(1, args);
                if(new_args) {
                    PyObject *s = PyString_Format(err_msg, new_args);
                    if(s) {
                        PyErr_SetString(PyExc_TypeError, PyString_AsString(s));
                        Py_CLEAR(s);
                    }
                    Py_CLEAR(new_args);
                }
                Py_CLEAR(err_msg);
            }
            goto cleanup;
        }
        result = pkgcore_cpv_parse_from_cpvstr(self, category, versioned);
    }
    if(result == 2)
        goto cleanup;
    else if (result == 1)
        goto parse_error;

    return 0;

parse_error:
    // yay.  well, set an exception.
    // if an error from trying to call, let it propagate.  meanwhile, we
    // cleanup our own
    if(package) {
        if(PySequence_Length(fullver) != 0) {
            cpvstr = PyString_FromFormat("%s/%s-%s", PyString_AsString(category),
                PyString_AsString(package), PyString_AsString(fullver));
        } else {
            cpvstr = PyString_FromFormat("%s/%s", PyString_AsString(category),
                PyString_AsString(package));
        }
        if(!cpvstr)
            goto cleanup;
    } else {
        cpvstr = category;
    }
    PyObject *tmp = PyObject_CallFunction(pkgcore_InvalidCPV_Exc, "O", cpvstr);
    if(package) {
        Py_DECREF(cpvstr);
    }
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
    if(other->version == NULL)
        return 1;

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
        return NULL;
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
        return NULL;
    s = PyObject_Repr(cpv);
    Py_DECREF(cpv);
    if(!s)
        return NULL;
    char *str = PyString_AsString(s);
    if(!s) {
        Py_DECREF(s);
        return NULL;
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
    0,                                /* tp_itemsize */
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
    pkgcore_cpv_members,              /* tp_members */
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


PyMODINIT_FUNC
init_cpv(void)
{
    PyObject *m, *s, *errors;

    m = Py_InitModule3("_cpv", NULL, pkgcore_cpv_documentation);
    if (!m)
        return;

    // this may be redundant; do this so __builtins__["__import__"] is used.
    s = PyString_FromString("pkgcore.ebuild.errors");
    if (!s)
        return;

    errors = PyImport_Import(s);
    Py_DECREF(s);
    if (!errors)
        return;

    pkgcore_InvalidCPV_Exc = PyObject_GetAttrString(errors, "InvalidCPV");
    if (!pkgcore_InvalidCPV_Exc)
        return;

    pkgcore_cpvType.ob_type = &PyType_Type;

    if (PyType_Ready(&pkgcore_cpvType) < 0)
        return;

    Py_INCREF(&pkgcore_cpvType);
    if (PyModule_AddObject(m, "CPV", (PyObject *)&pkgcore_cpvType) == -1)
        return;

    PyObject *cobject = PyCObject_FromVoidPtrAndDesc(
        &pkgcore_cpv_heapdefs, "NyHeapDef[] v1.0", 0);
    if (!cobject)
        return;

    if (PyModule_AddObject(m, "_NyHeapDefs_", cobject) == -1)
        return;

    /* Success! */
}
