/*
 * Copyright: 2006 Brian Harring <ferringb@gmail.com>
 * License: GPL2
 *
 * C version of cpv class for speed.
 */

#include <Python.h>
#include <structmember.h>
#include <string.h>

// dev-util/diffball-cvs.2006.0_alpha1_alpha2
// dev-util/diffball

#define ISDIGIT(c) ('0' <= (c) && '9' >= (c))
#define ISALPHA(c) (('a' <= (c) && 'z' >= (c)) || ('A' <= (c) && 'Z' >= (c)))
#define ISLOWER(c) ('a' <= (c) && 'z' >= (c))
#define ISALNUM(c) (ISALPHA(c) || ISDIGIT(c))

typedef enum { SUF_ALPHA=0, SUF_BETA, SUF_PRE, SUF_RC, SUF_NORM, SUF_P } version_suffixes;
const char * const version_suffixes_str[] = {"alpha", "beta", "pre", "rc", "", "p", NULL};

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
	PyObject *cpvstr;
	PyObject *category;
	PyObject *package;
	PyObject *key;
	PyObject *fullver;
	PyObject *version;
	PyObject *revision;
	unsigned long *suffixes;
	int cvs;
} pkgcore_cpv;

static PyObject *pkgcore_InvalidCPV_Exc = NULL;

#define PKGCORE_IMMUTABLE_ATTRIBUTE(getter, setter, name, attribute)		\
static int									\
setter (pkgcore_cpv *self, PyObject *v, void *closure)				\
{										\
	PyErr_SetString(PyExc_AttributeError, name" is immutable");		\
	return -1;								\
};										\
										\
static PyObject *								\
getter (pkgcore_cpv *self, void *closure)					\
{										\
	Py_INCREF(self->attribute);						\
	return self->attribute;							\
}

PKGCORE_IMMUTABLE_ATTRIBUTE(pkgcore_cpv_get_cpvstr,   pkgcore_cpv_set_cpvstr,   "cpvstr", cpvstr);
PKGCORE_IMMUTABLE_ATTRIBUTE(pkgcore_cpv_get_category, pkgcore_cpv_set_category, "category", category);
PKGCORE_IMMUTABLE_ATTRIBUTE(pkgcore_cpv_get_package,  pkgcore_cpv_set_package,  "package", package);
PKGCORE_IMMUTABLE_ATTRIBUTE(pkgcore_cpv_get_fullver,  pkgcore_cpv_set_fullver,  "fullver", fullver);
PKGCORE_IMMUTABLE_ATTRIBUTE(pkgcore_cpv_get_version,  pkgcore_cpv_set_version,  "version", version);
PKGCORE_IMMUTABLE_ATTRIBUTE(pkgcore_cpv_get_revision, pkgcore_cpv_set_revision, "revision", revision);
PKGCORE_IMMUTABLE_ATTRIBUTE(pkgcore_cpv_get_key, pkgcore_cpv_set_key, "key", key);

#undef PKGCORE_IMMUTABLE_ATTRIBUTE


static PyGetSetDef pkgcore_cpv_getsetters[] = {
	{"cpvstr",   (getter)pkgcore_cpv_get_cpvstr,   (setter)pkgcore_cpv_set_cpvstr,   "cpvstr", NULL},
	{"category", (getter)pkgcore_cpv_get_category, (setter)pkgcore_cpv_set_category, "category", NULL},
	{"package",  (getter)pkgcore_cpv_get_package,  (setter)pkgcore_cpv_set_package,  "package", NULL},
	{"key",      (getter)pkgcore_cpv_get_key,      (setter)pkgcore_cpv_set_key,      "key", NULL},
	{"fullver",  (getter)pkgcore_cpv_get_fullver,  (setter)pkgcore_cpv_set_fullver,  "fullver", NULL},
	{"version",  (getter)pkgcore_cpv_get_version,  (setter)pkgcore_cpv_set_version,  "version", NULL},
	{"revision", (getter)pkgcore_cpv_get_revision, (setter)pkgcore_cpv_set_revision, "revision", NULL},
	{NULL}
};


static PyObject *
pkgcore_cpv_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	pkgcore_cpv *self;
	self = (pkgcore_cpv *)type->tp_alloc(type, 0);
	if(NULL == self)
		return (PyObject *)self;

	#define PKGCORE_CPV_INIT_ATTR(attr)	\
	Py_INCREF(Py_None);			\
	self->attr = Py_None;

	PKGCORE_CPV_INIT_ATTR(cpvstr);
	PKGCORE_CPV_INIT_ATTR(category);
	PKGCORE_CPV_INIT_ATTR(package);
	PKGCORE_CPV_INIT_ATTR(fullver);
	PKGCORE_CPV_INIT_ATTR(version);
	PKGCORE_CPV_INIT_ATTR(revision);
	PKGCORE_CPV_INIT_ATTR(key);
	#undef PKGCORE_CPV_INIT_ATTR
	self->cvs = 0;
	self->suffixes = NULL;
	return (PyObject *)self;
}

	
static int
//pkgcore_cpv_init(pkgcore_cpv *self, const char *cpvstring, char parse_cat, char parse_pkg)
pkgcore_cpv_init(pkgcore_cpv *self, PyObject *args, PyObject *kwds)
{
	int result = 0;
	char *ver_start = NULL;
	char *p = NULL, *s1 = NULL, *s2 = NULL;
	char *start = NULL;
	PyObject *tmp = NULL, *tmp2 = NULL, *category = NULL, *package = NULL, *cpvstr = NULL;

	static char *kwlist[] = {"cpvstr", "category", "package", NULL};
	if(! PyArg_ParseTupleAndKeywords(args, kwds, "S|SS", kwlist,
		&cpvstr, &category, &package)) {
		return -1;
	}
	
	start = p = PyString_AsString(cpvstr);
	if(NULL == start)
		return -1;

	if(NULL == category && NULL == package) {
		tmp = cpvstr;
		Py_INCREF(tmp);
	} else if (NULL == package) {
		s1 = PyString_AsString(category);
		if(!s1)
			goto cleanup;
		tmp = PyString_FromFormat("%s/%s", s1, start);
		if(!tmp)
			goto cleanup;
	} else {
		s1 = PyString_AsString(category);
		if(!s1)
			goto cleanup;
		s2 = PyString_AsString(package);
		if(!s2)
			goto cleanup;
		tmp = PyString_FromFormat("%s/%s-%s", s1, s2, start);
		if(!tmp)
			goto cleanup;
	}
	tmp2 = self->cpvstr;
	self->cpvstr = tmp;
	Py_DECREF(tmp2);

	if(NULL != category) {
		// verify it first.
		s1 = PyString_AsString(category);
		if(!s1)
			goto parse_error;
		if('\0' == *s1)
			goto parse_error;
		while(ISALNUM(*s1) || '+' == *s1 || '-' == *s1)
			s1++;
		if('\0' != *s1)
			goto parse_error;
		tmp = self->category;
		Py_INCREF(category);
		self->category = category;
		Py_DECREF(tmp);
	} else {
		// ok, we need to eat the cat from the cpvstring.
		// allowed pattern [a-zA-Z0-9+-]+/
		while('\0' != *p && '/' != *p && (ISALNUM(*p) || '+' == *p || '-' == *p))
			p++;
		if(p - start <= 1 || '/' != *p) {
			// just /, or nothing
			goto parse_error;
		}
		if('\0' == *p)
			goto parse_error;
		tmp = PyString_FromStringAndSize(start, p - start);
		if(!tmp) {
			result = -1;
			goto cleanup;
		}
		tmp2 = self->category;
		self->category = tmp;
		Py_DECREF(tmp2);
		p++;
		if('\0' == *p)
			goto parse_error;
		start = p;
	}

	if(NULL != package) {
		ver_start = p;
		tmp = self->package;
		Py_INCREF(package);
		self->package = package;
		Py_DECREF(tmp);
	} else {
		// yay- need to eat the pkg next
		// allowed [a-zA-Z0-9](?:[-_+a-zA-Z0-9]*?[+a-zA-Z0-9])??)
		// ver-  "(?:-(?P<fullver>(?P<version>(?:cvs\\.)?(?:\\d+)(?:\\.\\d+)*[a-z]?(?:_(p(?:re)?|beta|alpha|rc)\\d*)*)" +
		// "(?:-r(?P<revision>\\d+))?))?$")
		// note that pkg regex is non-greedy.
		start = p;
		p = strchr(start, '-');
		while(NULL != p) {
			++p;
			ver_start = p;
			if('\0' == *p)
				goto parse_error;
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
			// no pkg detected, find end, verification happens outside the block
			p = start;
			while('\0' != *p)
				p++;
			ver_start = p;
		} else {
			p = ver_start;
			p--;
		}
		tmp = PyString_FromStringAndSize(start, p - start);
		if(!tmp) {
			result = -1;
			goto cleanup;
		}
		tmp2 = self->package;
		self->package = tmp;
		Py_DECREF(tmp2);
	}
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

	// ok. it's good.  note the key setting; if no ver, just reuse cpvstr

	if('\0' == *ver_start) {
		// no version.

		Py_INCREF(self->cpvstr);
		tmp = self->key;
		self->key = self->cpvstr;
		Py_DECREF(tmp);

		Py_INCREF(Py_None);
		tmp = self->fullver;
		self->fullver = Py_None;
		Py_DECREF(tmp);

		Py_INCREF(Py_None);
		tmp = self->version;
		self->version = Py_None;
		Py_DECREF(tmp);

		Py_INCREF(Py_None);
		tmp = self->revision;
		self->revision = Py_None;
		Py_DECREF(tmp);

		return 0;
	}

	tmp = PyString_FromFormat("%s/%s", PyString_AsString(self->category), PyString_AsString(self->package));
	if(!tmp)
		goto cleanup;
	tmp2 = self->key;
	self->key = tmp;
	Py_DECREF(tmp2);

	// version parsing.
	// "(?:-(?P<fullver>(?P<version>(?:cvs\\.)?(?:\\d+)(?:\\.\\d+)*[a-z]?(?:_(p(?:re)?|beta|alpha|rc)\\d*)*)" +
	// "(?:-r(?P<revision>\\d+))?))?$")
	p = ver_start;

	// suffixes _have_ to have versions; do it now to avoid
	if('_' == *p)
		goto parse_error;

	// grab cvs chunk
	if(0 == strncmp(ver_start, "cvs.", 4)) {
		self->cvs = 1;
		p += 4;
		if('\0' == *p)
			goto parse_error;
	}
	// (\d+)(\.\d+)*[a-z]?
	for(;;) {
		while(ISDIGIT(*p))
			p++;
		if(ISALPHA(*p)) {
			p++;
			if('\0' != *p && '_' != *p && '-' != *p)
				goto parse_error;
			break;
		} else if('.' == *p) {
			p++;
		} else if('\0' == *p || '_' == *p || '-' == *p) {
			break;
		} else {
			goto parse_error;
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
			result = -1;
			goto cleanup;
		}
		suffix_count *= 2;
		for(pos = 0; pos < suffix_count; pos += 2) {
			p += 1; // skip the leading _
			if('\0' == *p)
				goto parse_error;
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
						goto parse_error;
					self->suffixes[pos + 1] = new_long;
					break;
				}
			}
			if(NULL == sv->str) {
				// that means it didn't find the suffix.
				goto parse_error;
			}
		}
		self->suffixes[pos] = PKGCORE_EBUILD_SUFFIX_DEFAULT_SUF;
		self->suffixes[pos + 1] = PKGCORE_EBUILD_SUFFIX_DEFAULT_VAL;
	} else {
		self->suffixes = (unsigned long *)pkgcore_ebuild_default_suffixes;
	}
	if('\0' != *p && '-' != *p)
		goto cleanup;
	if(ver_start != p) {
		tmp = PyString_FromStringAndSize(ver_start, p - ver_start);
		if(!tmp)
			goto cleanup;
		tmp2 = self->version;
		self->version = tmp;
		Py_DECREF(tmp2);
	}
	if('-' == *p) {
		unsigned long revision = 0;
		// ok, revision.
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
		Py_DECREF(tmp2);
		tmp = PyString_FromStringAndSize(ver_start, p - ver_start);
		if(!tmp)
			goto cleanup;
		tmp2 = self->fullver;
		self->fullver = tmp;
		Py_DECREF(tmp2);
	} else {
		Py_INCREF(self->version);
		tmp2 = self->fullver;
		self->fullver = self->version;
		Py_DECREF(tmp2);

		Py_INCREF(Py_None);
		tmp = self->revision;
		self->revision = Py_None;
		Py_DECREF(tmp);
		
	}
	return 0;

parse_error:
	// yay.  well, set an exception.
	// if an error from trying to call, let it propagate.  meanwhile, we cleanup our own
	tmp = PyObject_CallFunction(pkgcore_InvalidCPV_Exc, "O", self->cpvstr);
	if(NULL != tmp) {
		PyErr_SetObject(pkgcore_InvalidCPV_Exc, tmp);
		Py_DECREF(tmp);
	} 
cleanup:
	#define dealloc_attr(attr)	\
	Py_XDECREF(self->attr); self->attr = NULL;
	dealloc_attr(cpvstr);
	dealloc_attr(category);
	dealloc_attr(package);
	dealloc_attr(key);
	dealloc_attr(version);
	dealloc_attr(revision);
	dealloc_attr(fullver);
	#undef dealloc_attr

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
	#define dealloc_attr(attr)	\
	Py_XDECREF(self->attr); self->attr = NULL;
	dealloc_attr(cpvstr);
	dealloc_attr(category);
	dealloc_attr(package);
	dealloc_attr(key);
	dealloc_attr(version);
	dealloc_attr(revision);
	dealloc_attr(fullver);
	#undef dealloc_attr
	
	if(NULL != self->suffixes) {
		if(PKGCORE_EBUILD_SUFFIX_DEFAULT_SUF != self->suffixes[0]) {
			PyObject_Free(self->suffixes);
		}
		self->suffixes = NULL;
	}
	self->ob_type->tp_free((PyObject *)self);
}


static int
pkgcore_cpv_compare(pkgcore_cpv *self, pkgcore_cpv *other)
{
	int c;
	c = PyObject_Compare(self->category, other->category);
	if(PyErr_Occurred())
		return -1;
	if(c != 0)
		return c;
	c = PyObject_Compare(self->package, other->package);
	if(PyErr_Occurred())
		return -1;
	if(c != 0)
		return c;
	if(self->version == Py_None)
		return other->version == Py_None ? 0 : -1;
	
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
			// terminator.  one remaining element, but little point in testing it.
			// to have hit here requires them to be the same also (for those wondering why we're not testing)
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
	return PyObject_Compare(self->revision, other->revision);
}
	


static long
pkgcore_cpv_hash(pkgcore_cpv *self)
{
	return PyObject_Hash(self->cpvstr);
}


static PyObject *
pkgcore_cpv_str(pkgcore_cpv *self)
{
	PyObject *s;
	if(self->cpvstr == Py_None) {
		Py_INCREF(Py_None);
		s = PyObject_Str(Py_None);
		Py_DECREF(Py_None);
	} else {
		s = self->cpvstr;
		Py_INCREF(s);
	}
	return s;
}


static PyObject *
pkgcore_cpv_repr(pkgcore_cpv *self)
{
	PyObject *s;
	if(self->cpvstr == Py_None) {
		Py_INCREF(Py_None);
		s = PyObject_Repr(Py_None);
		Py_DECREF(Py_None);
	} else {
		s = PyObject_Repr(self->cpvstr);
		if(!s)
			return (PyObject *)NULL;
		char *str = PyString_AsString(s);
		if(!s) {
			Py_DECREF(s);
			return (PyObject *)NULL;
		}
		PyObject *s2 = PyString_FromFormat("CPV(%s)", str);
		Py_DECREF(s);
		s = s2;
	}
	return s;
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
	pkgcore_cpv_new,                  /* tp_new */
};

PyDoc_STRVAR(
	pkgcore_cpv_documentation,
	"C reimplementation of pkgcore.package.cpv.");

#ifndef PyMODINIT_FUNC	/* declarations for DLL import/export */
#define PyMODINIT_FUNC void
#endif
PyMODINIT_FUNC
init_cpv(void)
{
	PyObject *m, *s;
	
	// this may be redundant; do this so __builtins__["__import__"] is used.
	s = PyString_FromString("pkgcore.package.errors");
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
}
