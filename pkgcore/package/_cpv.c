#include <Python.h>
#include <structmember.h>
#include <string.h>

// dev-util/diffball-cvs.2006.0_alpha1_alpha2
// dev-util/diffball


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

#undef PKGCORE_IMMUTABLE_ATTRIBUTE


static PyGetSetDef pkgcore_cpv_getsetters[] = {
	{"cpvstr", (getter)pkgcore_cpv_get_cpvstr, (setter)pkgcore_cpv_set_cpvstr, "cpvstr", NULL},
	{"category", (getter)pkgcore_cpv_get_category, (setter)pkgcore_cpv_set_category, "category", NULL},
	{"package", (getter)pkgcore_cpv_get_package, (setter)pkgcore_cpv_set_package, "package", NULL},
	{"fullver", (getter)pkgcore_cpv_get_fullver, (setter)pkgcore_cpv_set_fullver, "fullver", NULL},
	{"version", (getter)pkgcore_cpv_get_version, (setter)pkgcore_cpv_set_version, "version", NULL},
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
	Py_INCREF(tmp);
	self->cpvstr = tmp;
	Py_DECREF(tmp2);

	if(NULL != category) {
		// verify it first.
		s1 = PyString_AsString(category);
		if(!s1)
			goto parse_error;
		if('\0' == *s1)
			goto parse_error;
		while('\0' != *s1 && (isalnum(*s1) || '+' == *s1 || '-' == *s1))
			s1++;
		if(*s1 != '\0')
			goto parse_error;
		tmp = self->category;
		Py_INCREF(category);
		self->category = category;
		Py_DECREF(tmp);
	} else {
		// ok, we need to eat the cat from the cpvstring.
		// allowed pattern [a-zA-Z0-9+-]+/
		while('\0' != *p && '/' != *p && (isalnum(*p) || '+' == *p || '-' == *p))
			p++;
		if(p - start <= 1) {
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
			while('\0' != *p && isdigit(*p))
				p++;
			if(p == ver_start) {
				p = strchr(ver_start + 1, '-');
				continue;
			}
			if('\0' == *p)
				break;
			
			// ok.  so, either it's a period, _, or a *single* [a-z].
			if('.' == *p || '_' == *p) {
				break;
			} else if(islower(*p)) {
				p++;
				if('\0' == *p || '.' == *p || '_' == *p)
					break;
			}
			p = strchr(p, '-');
		}
		// do verification of pkg for *both* branches
		if (!p) {
			// no pkg detected
			// verify it's valid chars then.
			p = start;
			while('\0' != *p && (isalnum(*p) || '-' == *p || '_' == *p || '+' == *p))
				p++;
			if('\0' != *p)
				goto parse_error;
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
	if(!isalnum(*s2))
		goto parse_error;
	s2++;
	while('\0' != s2 && (isalnum(*s2) || '+' == *s2 || '-' == *s2 || '_' == *s2))
		s2++;
	if('\0' != *s2 || s2 - s1 < 2)
		goto parse_error;
	if(!isalnum(*(s2 - 1)))
		goto parse_error;
	// ok. it's good.

	if('\0' == *ver_start) {
		// no version.
		Py_INCREF(Py_None);
		self->fullver = Py_None;
		Py_INCREF(Py_None);
		self->version = Py_None;
		Py_INCREF(Py_None);
		self->revision = Py_None;
		return 0;
	}
	// version parsing.
	// "(?:-(?P<fullver>(?P<version>(?:cvs\\.)?(?:\\d+)(?:\\.\\d+)*[a-z]?(?:_(p(?:re)?|beta|alpha|rc)\\d*)*)" +
	// "(?:-r(?P<revision>\\d+))?))?$")
	p = ver_start;
	// grab cvs chunk
	if(0 == strncmp(ver_start, "cvs.", 4)) {
		self->cvs = 1;
		p += 4;
		if('\0' == *p)
			goto parse_error;
	}
	// (\d+)(\.\d+)*[a-z]?
	for(;;) {
		while('\0' != *p && isdigit(*p))
			p++;
		if(isalpha(*p)) {
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
		unsigned int pos = 0;
		unsigned new_long;
		struct suffix_ver *sv;
		while(p != NULL) {
			suffix_count++;
			p = strchr(p + 1, '_');
		}
		// trailing is 0 0
		p = orig_p;
		self->suffixes = PyObject_Malloc(sizeof(long) * (suffix_count + 1) * 2);
		if(NULL == self->suffixes) {
			// wanker.
			PyErr_NoMemory();
			result = -1;
			goto cleanup;
		}
		p++;
		suffix_count *= 2;
		while(pos < suffix_count) {
			if('\0' == *p)
				goto parse_error;
			for(sv = pkgcore_ebuild_suffixes; NULL != sv->str; sv++) {
				if(0 == strncmp(p, sv->str, sv->str_len)) {
					self->suffixes[pos] = sv->val;
					p += sv->str_len;
					new_long = 0;
					while('\0' != *p && isdigit(*p)) {
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
			pos += 2;
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
		while('\0' != *p && isdigit(*p)) {
			revision = (revision * 10) + *p - '0';
			p++;
		}
		if('\0' != *p)
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
	}
	return 0;

parse_error:
	// yay.  well, set an exception.
	tmp = PyObject_CallFunction(pkgcore_InvalidCPV_Exc, "O", self->cpvstr);
	if(!tmp) {
		// fricker- let it's error propagate.
		return -1;
	}
	PyErr_SetObject(pkgcore_InvalidCPV_Exc, tmp);
cleanup:
	Py_XDECREF(self->cpvstr);
	self->cpvstr = NULL;
	Py_XDECREF(self->category);
	self->category = NULL;
	Py_XDECREF(self->package);
	self->package = NULL;
	Py_XDECREF(self->fullver);
	self->fullver = NULL;
	Py_XDECREF(self->version);
	self->version = NULL;
	Py_XDECREF(self->revision);
	self->revision = NULL;
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
	Py_XDECREF(self->cpvstr);
	self->cpvstr = NULL;
	Py_XDECREF(self->category);
	self->category = NULL;
	Py_XDECREF(self->package);
	self->package = NULL;
	Py_XDECREF(self->fullver);
	self->fullver = NULL;
	Py_XDECREF(self->version);
	self->version = NULL;
	Py_XDECREF(self->revision);
	self->revision = NULL;
	if(NULL != self->suffixes) {
		if(PKGCORE_EBUILD_SUFFIX_DEFAULT_SUF != self->suffixes[0]) {
			PyObject_Free(self->suffixes);
		}
		self->suffixes = NULL;
	}
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
			} while (isdigit(*s1) && isdigit(*o1));

			while(isdigit(*s1)) {
				if('0' != *s1)
					return +1;
				s1++;
			}
			while(isdigit(*o1)) {
				if('0' != *o1)
					return -1;
				o1++;
			}
		} else {
			// int comparison rules.
			char *s_start = s1, *o_start = o1;

			while(isdigit(*s1))
				s1++;
			while(isdigit(*o1))
				o1++;

			if((s1 - s_start) < (o1 - o_start))
				return -1;
			else if((s1 - s_start) > (o1 - o_start))
				return 1;
			
			char *s_end = s1;

			s1 = s_start;
			o1 = o_start;
			for(s1 = s_start, o1 = o_start; s1 != s_end; s1++, o1++) {
				if(*s1 < *o1)
					return -1;
				else if (*s1 > *o1)
					return 1;
			}
		}
		if(isalpha(*s1)) {
			if(isalpha(*o1)) {
				if(*s1 < *o1)
					return -1;
				else if(*s1 > *o1)
					return 1;
			} else
				return 1;
		} else if isalpha(*o1) {
			return -1;
		}
		if('.' == *s1)
			s1++;
		if('.' == *o1)
			o1++;
		// hokay.  no resolution there.
	}
	// ok.  one of the two just ran out of vers; test on suffixes
	if('_' == *s1) {
		if('_' != *o1)
			return +1;
	} else if('_' == *o1) {
		return -1;
	}
	
	// bugger.  exact same version string up to suffix.
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
	pkgcore_cpv_compare,              /* tp_compare */
	0,                                /* tp_repr */
	0,                                /* tp_as_number */
	0,                                /* tp_as_sequence */
	0,                                /* tp_as_mapping */
	(hashfunc)pkgcore_cpv_hash,       /* tp_hash */
	0,                                /* tp_call */
	0,                                /* tp_str */
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
