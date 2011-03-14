/*
 * Copyright: 2006-2011 Brian Harring <ferringb@gmail.com>
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
#include <ctype.h>

// exceptions, loaded during initialization.
static PyObject *pkgcore_atom_MalformedAtom_Exc = NULL;
static PyObject *pkgcore_atom_InvalidCPV_Exc = NULL;

// restricts.
static PyObject *pkgcore_atom_VersionMatch = NULL;
static PyObject *pkgcore_atom_SlotDep = NULL;
static PyObject *pkgcore_atom_RepositoryDep = NULL;
static PyObject *pkgcore_atom_CategoryDep = NULL;
static PyObject *pkgcore_atom_PackageDep = NULL;
static PyObject *pkgcore_atom_mk_use = NULL;
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
static PyObject *pkgcore_atom_cpv_parse_versioned = NULL;
static PyObject *pkgcore_atom_cpv_parse_unversioned = NULL;
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
static PyObject *pkgcore_atom_blocks_strongly = NULL;
static PyObject *pkgcore_atom_op = NULL;
static PyObject *pkgcore_atom_negate_vers = NULL;
static PyObject *pkgcore_atom_restrictions = NULL;
static PyObject *pkgcore_atom_transitive_use_atom_str = NULL;
static PyObject *pkgcore_atom__class__ = NULL;


#define VALID_SLOT_CHAR(c) (isalnum(c) || '-' == (c) \
	|| '_' == (c) || '.' == (c) || '+' == (c))
#define INVALID_SLOT_FIRST_CHAR(c) ('.' == (c) || '-' == (c))

#define VALID_USE_CHAR(c) (isalnum(c) || '-' == (c) \
	|| '_' == (c) || '@' == (c) || '+' == (c))

#define VALID_REPO_CHAR(c) (isalnum(c) || '-' == (c) || '_' == (c) || '/' == (c))
#define INVALID_REPO_FIRST_CHAR(c) ('-' == (c))

static void
Err_SetMalformedAtom(PyObject *atom_str, char *raw_msg)
{
	PyObject *msg = PyString_FromString(raw_msg);
	if(!msg)
		return;
	PyObject *err = PyObject_CallFunctionObjArgs(
		pkgcore_atom_MalformedAtom_Exc, atom_str, msg, NULL);
	Py_DECREF(msg);
	if(err) {
		PyErr_SetObject(pkgcore_atom_MalformedAtom_Exc, err);
		Py_DECREF(err);
	}
}


static int
reset_class(PyObject *self)
{
	PyObject *kls;
	if(NULL == (kls = PyObject_GetAttr(self, pkgcore_atom_transitive_use_atom_str)))
		return 1;
	if(PyObject_GenericSetAttr(self, pkgcore_atom__class__, kls)) {
		Py_DECREF(kls);
		return 1;
	}
	Py_DECREF(kls);
	return 0;
}

// -1 for error
// 0 for nontransitive
// 1 for transitive detected (thus class switch needed)

static int
parse_use_deps(PyObject *atom_str, char **p_ptr, PyObject **use_ptr)
{
	char *p = *p_ptr;
	char *start = p;
	char *use_start, *use_end;
	char transitive_detected = 0;
	Py_ssize_t len = 1;
	PyObject *use = NULL;

	// first find the length of tuple we need
	use_start = p;
	for(;;p++) {
		if('\0' == *p) {
			Err_SetMalformedAtom(atom_str,
				"unclosed use dep");
			return -1;
		} else if (',' == *p || ']' == *p) {
			// we flip p back one for ease of coding; rely on compiler
			// to optimize it out.
			use_end = p - 1;
			if(use_end > use_start) {
				if('-' == *use_start) {
					use_start++;
				} else if('?' == *use_end || '=' == *use_end) {
					use_end--;
					// commutative use.  ! leading is allowed
					if(use_start != use_end && '!' == *use_start) {
						use_start++;
					}
					transitive_detected = 1;
				}
			}
			if(use_end < use_start) {
				Err_SetMalformedAtom(atom_str,
					"empty use flag detected");
				return -1;
			} else if(!isalnum(*use_start)) {
				Err_SetMalformedAtom(atom_str,
					"first char of a use flag must be alphanumeric");
				return -1;
			}
			while(use_start <= use_end) {
				if(!VALID_USE_CHAR(*use_start)) {
					Err_SetMalformedAtom(atom_str,
						"invalid char in use dep; each flag must be a-Z0-9_@-+");
					return -1;
				}
				use_start++;
			}
			if(']' == *p) {
				break;
			}
			len++;
			use_start = p + 1;
		}
	}
	// and now we're validated.
	char *end = p;
	if(len == 1)
		use = PyTuple_New(len);
	else
		use = PyList_New(len);
	if(!use)
		return -1;
	Py_ssize_t idx = 0;
	PyObject *s;
	p = start;
	for(;idx < len;idx++) {
		use_start = p;
		while(',' != *p && ']' != *p)
			p++;
		if(!(s = PyString_FromStringAndSize(use_start, p - use_start))) {
			goto cleanup_use_processing;
		}
		if(len != 1) {
			// steals the ref.
			if(PyList_SetItem(use, idx, s)) {
				Py_DECREF(s);
				goto cleanup_use_processing;
			}
		} else {
			PyTuple_SET_ITEM(use, idx, s);
		}
		p++;
	}
	if(len > 1) {
		// weak, but it's required for the tuple optimization
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
	*p_ptr = end;
	return transitive_detected;
	cleanup_use_processing:
	Py_CLEAR(use);
	return -1;
}

static int
parse_slot_deps(PyObject *atom_str, char **p_ptr, PyObject **slots_ptr)
{
	char *p = *p_ptr;
	char *start = p;
	char check_valid_first_char = 1;
	Py_ssize_t len = 1;
	PyObject *slots = NULL;
	while('\0' != *p && ':' != *p && '[' != *p) {
		if (',' == *p) {
			len++;
			check_valid_first_char = 1;
		} else if (check_valid_first_char) {
			if (INVALID_SLOT_FIRST_CHAR(*p)) {
				Err_SetMalformedAtom(atom_str,
					"invalid first char of slot dep; must not be '-'");
				goto cleanup_slot_processing;
			}
			check_valid_first_char = 0;
		} else if(!VALID_SLOT_CHAR(*p)) {
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
		if(len > 1) {
			// bugger. need a list :/
			PyObject *tmp = PyList_New(len);
			if(!tmp)
				goto cleanup_slot_processing;
			if(PyList_SetSlice(tmp, 0, len, slots)) {
				Py_DECREF(tmp);
				goto cleanup_slot_processing;
			} else if (PyList_Sort(tmp)) {
				Py_DECREF(tmp);
				goto cleanup_slot_processing;
			}
			for(idx=0; idx < len; idx++) {
				PyTuple_SET_ITEM(slots, idx, PyList_GET_ITEM(tmp, idx));
			}
			Py_DECREF(tmp);
		}
		*slots_ptr = slots;
		*p_ptr = p;
		return 0;
	}
	cleanup_slot_processing:
	Py_CLEAR(slots);
	return 1;
}

static int
parse_repo_id(PyObject *atom_str, char **p_ptr, PyObject **repo_id)
{
	char *p = *p_ptr;
	while('\0' != *p && '[' != *p) {
		if(p == *p_ptr && INVALID_REPO_FIRST_CHAR(*p)) {
			Err_SetMalformedAtom(atom_str,
				"invalid first char of repo_id: "
				"must not be '-'");
			return 1;
		} else if(!VALID_REPO_CHAR(*p)) {
			Err_SetMalformedAtom(atom_str,
				"invalid char in repo_id: "
				"valid characters are [a-Z0-9_-/]");
			return 1;
		}
		p++;
	}

	if(*p_ptr == p) {
		Err_SetMalformedAtom(atom_str,
			"repo_id must not be empty");
		return 1;
	}
	*repo_id = PyString_FromStringAndSize(*p_ptr, p - *p_ptr);
	*p_ptr = p;
	return *repo_id ? 0 : 1;
}

static int
parse_cpv(PyObject *atom_str, PyObject *cpv_str, PyObject *self,
	int has_version, int *had_revision)
{
	PyObject *tmp, *cpv;
	cpv = PyObject_CallFunctionObjArgs(
		has_version ? pkgcore_atom_cpv_parse_versioned :
			pkgcore_atom_cpv_parse_unversioned,
		cpv_str, NULL);
	if(!cpv) {
		PyObject *type, *exc, *tb;
		PyErr_Fetch(&type, &exc, &tb);
		PyErr_NormalizeException(&type, &exc, &tb);

		if(!exc)
			return 1;

		tmp = PyObject_Str(exc);
		Py_DECREF(type);
		Py_DECREF(exc);
		Py_XDECREF(tb);

		if(!tmp)
			return 1;

		Err_SetMalformedAtom(atom_str, PyString_AsString(tmp));
		Py_DECREF(tmp);
		return 1;
	}

	#define STORE_ATTR(attr_name)								   \
		if(NULL == (tmp = PyObject_GetAttr(cpv, attr_name))){ \
			goto parse_cpv_error;								   \
		}														   \
		if(PyObject_GenericSetAttr(self, attr_name, tmp)) {		  \
			Py_DECREF(tmp);										 \
			goto parse_cpv_error;								   \
		}														   \
		Py_DECREF(tmp);

	STORE_ATTR(pkgcore_atom_cpvstr);
	STORE_ATTR(pkgcore_atom_category);
	STORE_ATTR(pkgcore_atom_package);
	STORE_ATTR(pkgcore_atom_key);
	tmp = PyObject_GetAttr(cpv, pkgcore_atom_fullver);
	if(!tmp)
		goto parse_cpv_error;
	if(PyErr_Occurred()) {
		Py_DECREF(tmp);
		goto parse_cpv_error;
	}
	if(PyObject_GenericSetAttr(self, pkgcore_atom_fullver, tmp)) {
		Py_DECREF(tmp);
		goto parse_cpv_error;
	}
	Py_DECREF(tmp);
	if(has_version) {
		STORE_ATTR(pkgcore_atom_version);
		if(NULL == (tmp = PyObject_GetAttr(cpv, pkgcore_atom_revision))) {
			goto parse_cpv_error;
		}
		*had_revision = (Py_None != tmp);
		if(PyObject_GenericSetAttr(self, pkgcore_atom_revision, tmp)) {
			Py_DECREF(tmp);
			goto parse_cpv_error;
		}
		Py_DECREF(tmp);
	} else {
		if(PyObject_GenericSetAttr(self, pkgcore_atom_version, Py_None))
			goto parse_cpv_error;
		if(PyObject_GenericSetAttr(self, pkgcore_atom_revision, Py_None))
			goto parse_cpv_error;
		*had_revision = 1;
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
	int eapi_int = -1;
	int had_revision = 0;
	static char *kwlist[] = {"atom_str", "negate_vers", "eapi", NULL};
	if(!PyArg_ParseTupleAndKeywords(args, kwds, "S|Oi:atom_init", kwlist,
		&atom_str, &negate_vers, &eapi_int))
		return NULL;

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
		if('!' == *p && (eapi_int != 0 && eapi_int != 1)) {
			blocks++;
			p++;
		}
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
	while('\0' != *p && ':' != *p && '[' != *p) {
		p++;
	}
	cpv_end = p;
	if(':' == *p) {
		p++;
		if('[' == *p) {
			Err_SetMalformedAtom(atom_str,
				"empty slot restriction isn't allowed");
			goto pkgcore_atom_parse_error;
		} else if(':' != *p) {
			if(parse_slot_deps(atom_str, &p, &slot)) {
				goto pkgcore_atom_parse_error;
			}
			if(':' == *p) {
				if(':' != p[1]) {
					Err_SetMalformedAtom(atom_str,
						"you can specify only one slot restriction");
					goto pkgcore_atom_parse_error;
				}
				p += 2;
				if(parse_repo_id(atom_str, &p, &repo_id)) {
					goto pkgcore_atom_parse_error;
				}
			}
		} else if(':' == *p) {
			// turns out it was a repo atom.
			p++;
			// empty slotting to get at a repo_id...
			if(parse_repo_id(atom_str, &p, &repo_id)) {
				goto pkgcore_atom_parse_error;
			}
		}
	}
	if('[' == *p) {
		p++;
		switch (parse_use_deps(atom_str, &p, &use)) {
			case -1:
				goto pkgcore_atom_parse_error;
				break;
			case 1:
				if(reset_class(self))
					goto pkgcore_atom_parse_error;
				break;
		}
		p++;
	}
	if('\0' != *p) {
		Err_SetMalformedAtom(atom_str,
			"trailing garbage detected");
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

	has_version = (op != pkgcore_atom_op_none);

	if(parse_cpv(atom_str, cpv_str, self, has_version, &had_revision)) {
		Py_DECREF(cpv_str);
		goto pkgcore_atom_parse_error;
	}
	Py_DECREF(cpv_str);

	// ok... everythings parsed... sanity checks on the atom.
	if(op == pkgcore_atom_op_droprev) {
		if(had_revision) {
			Err_SetMalformedAtom(atom_str,
				"revision isn't allowed with '~' operator");
			goto pkgcore_atom_parse_error;
		}
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

	if(0 == eapi_int) {
		if(Py_None != use) {
			Err_SetMalformedAtom(atom_str,
				"use deps aren't allowed in EAPI 0");
			goto pkgcore_atom_parse_error;
		} else if(Py_None != slot) {
			Err_SetMalformedAtom(atom_str,
				"slot deps aren't allowed in eapi 0");
			goto pkgcore_atom_parse_error;
		} else if(Py_None != repo_id) {
			Err_SetMalformedAtom(atom_str,
				"repository deps aren't allowed in eapi 0");
			goto pkgcore_atom_parse_error;
		}
	} else if(1 == eapi_int) {
		if(Py_None != use) {
			Err_SetMalformedAtom(atom_str,
				"use deps aren't allowed in eapi 1");
			goto pkgcore_atom_parse_error;
		}
	}
	if(eapi_int != -1 && Py_None != repo_id) {
		Err_SetMalformedAtom(atom_str,
			"repository deps aren't allowed in EAPI <=2");
		goto pkgcore_atom_parse_error;
	}
	if(eapi_int != -1 && Py_None != slot && PyTuple_GET_SIZE(slot) > 1) {
		Err_SetMalformedAtom(atom_str,
			"multiple slot deps aren't allowed in any supported EAPI");
		goto pkgcore_atom_parse_error;
	}

	#define STORE_ATTR(attr_name, val)			  \
	if(PyObject_GenericSetAttr(self, (attr_name), (val)))  \
		goto pkgcore_atom_parse_error;

	STORE_ATTR(pkgcore_atom_blocks, blocks ? Py_True : Py_False);
	STORE_ATTR(pkgcore_atom_blocks_strongly,
		(blocks && blocks != 2) ? Py_False : Py_True);
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
	return NULL;
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

static PyObject *
internal_pkgcore_atom_getattr(PyObject *self, PyObject *attr)
{
	int required = 2;
	int failed = 1;

	PyObject *op = NULL, *package = NULL, *category = NULL;
	PyObject *use = NULL, *slot = NULL, *repo_id = NULL;
	PyObject *tup = NULL, *tmp = NULL;
	PyObject *use_restrict = NULL;
	Py_ssize_t use_len = 0;

	// prefer Py_EQ since cpythons string optimizes that case.
	if(1 != PyObject_RichCompareBool(attr, pkgcore_atom_restrictions, Py_EQ)) {
		PyErr_SetObject(PyExc_AttributeError, attr);
		return NULL;
	}

	#define MUST_LOAD(ptr, str)					 \
	if(!((ptr) = PyObject_GetAttr(self, (str))))	\
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
	if(use != Py_None) {
		if (!(use_restrict = PyObject_CallFunctionObjArgs(pkgcore_atom_mk_use, use, NULL)))
			goto pkgcore_atom_getattr_error;
		if (-1 == (use_len = PyObject_Length(use_restrict)))
			goto pkgcore_atom_getattr_error;
		required += use_len;
	}
	if(slot != Py_None)
		required++;
	if(repo_id != Py_None)
		required++;

	tup = PyTuple_New(required);
	if(!tup)
		goto pkgcore_atom_getattr_error;

	int idx = 0;
	if(repo_id != Py_None) {
		if(!(tmp = PyObject_CallFunctionObjArgs(pkgcore_atom_RepositoryDep,
			repo_id, NULL)))
			goto pkgcore_atom_getattr_error;
		PyTuple_SET_ITEM(tup, 0, tmp);
		idx++;
	}

	if(!(tmp = PyObject_CallFunctionObjArgs(pkgcore_atom_PackageDep, package, NULL)))
		goto pkgcore_atom_getattr_error;
	PyTuple_SET_ITEM(tup, idx, tmp);
	idx++;

	if(!(tmp = PyObject_CallFunctionObjArgs(pkgcore_atom_CategoryDep, category, NULL)))
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
			if (! (tmp = PyObject_CallObject(pkgcore_atom_SlotDep, slot))) {
				goto pkgcore_atom_getattr_error;
			}
			PyTuple_SET_ITEM(tup, idx, tmp);
		}
		idx++;
	}
	if(use != Py_None) {
		Py_ssize_t x = 0;
		for (; x < use_len; x++, idx++) {
			if (!(tmp = PySequence_GetItem(use_restrict, x)))
				goto pkgcore_atom_getattr_error;
			PyTuple_SET_ITEM(tup, idx, tmp);
		}
	}
	failed = 0;
	pkgcore_atom_getattr_error:
	Py_XDECREF(op);
	Py_XDECREF(category);
	Py_XDECREF(package);
	Py_XDECREF(use);
	Py_XDECREF(slot);
	Py_XDECREF(repo_id);
	Py_XDECREF(use_restrict);
	if(failed)
		Py_CLEAR(tup);
	else {
		if(PyObject_GenericSetAttr(self, pkgcore_atom_restrictions, tup)) {
			Py_CLEAR(tup);
		}
	}
	return tup;
}

static PyObject *
pkgcore_atom_getattr_nondesc(PyObject *getattr_inst, PyObject *args)
{
	PyObject *self = NULL, *attr = NULL;
	if(!PyArg_ParseTuple(args, "OO", &self, &attr)) {
		return NULL;
	}
	return internal_pkgcore_atom_getattr(self, attr);
}

static PyObject *
pkgcore_atom_getattr_desc(PyObject *self, PyObject *args)
{
	PyObject *attr = NULL;
	if(!PyArg_ParseTuple(args, "O", &attr)) {
		return NULL;
	}
	return internal_pkgcore_atom_getattr(self, attr);
}

snakeoil_FUNC_BINDING("__init__", "pkgcore.ebuild._atom.__init__",
	pkgcore_atom_init, METH_VARARGS|METH_KEYWORDS)
snakeoil_FUNC_BINDING("__getattr__", "pkgcore.ebuild._atom.__getattr__nondesc",
	pkgcore_atom_getattr_nondesc, METH_O|METH_COEXIST)
snakeoil_FUNC_BINDING("__getattr__", "pkgcore.ebuild._atom.__getattr__desc",
	pkgcore_atom_getattr_desc, METH_VARARGS|METH_COEXIST)

PyDoc_STRVAR(
	pkgcore_atom_documentation,
	"cpython atom parsing functionality");


PyMODINIT_FUNC
init_atom(void)
{
	PyObject *tmp = NULL;

	if(PyType_Ready(&pkgcore_atom_init_type) < 0)
		return;

	if(PyType_Ready(&pkgcore_atom_getattr_desc_type) < 0)
		return;

	if(PyType_Ready(&pkgcore_atom_getattr_nondesc_type) < 0)
		return;

	snakeoil_LOAD_SINGLE_ATTR(pkgcore_atom_MalformedAtom_Exc, "pkgcore.ebuild.errors",
		"MalformedAtom");

	snakeoil_LOAD_MODULE(tmp, "pkgcore.ebuild.cpv");
	snakeoil_LOAD_ATTR(pkgcore_atom_cpv_parse_unversioned, tmp, "unversioned_CPV");
	snakeoil_LOAD_ATTR(pkgcore_atom_cpv_parse_versioned, tmp, "versioned_CPV");
	snakeoil_LOAD_ATTR(pkgcore_atom_InvalidCPV_Exc, tmp, "InvalidCPV");
	Py_CLEAR(tmp);

	snakeoil_LOAD_MODULE(tmp, "pkgcore.ebuild.restricts");
	snakeoil_LOAD_ATTR(pkgcore_atom_VersionMatch, tmp, "VersionMatch");
	snakeoil_LOAD_ATTR(pkgcore_atom_SlotDep, tmp, "SlotDep");
	snakeoil_LOAD_ATTR(pkgcore_atom_CategoryDep, tmp, "CategoryDep");
	snakeoil_LOAD_ATTR(pkgcore_atom_PackageDep, tmp, "PackageDep");
	snakeoil_LOAD_ATTR(pkgcore_atom_RepositoryDep, tmp, "RepositoryDep");
	snakeoil_LOAD_ATTR(pkgcore_atom_mk_use, tmp, "_parse_nontransitive_use");
	Py_CLEAR(tmp);

	snakeoil_LOAD_MODULE(tmp, "pkgcore.restrictions.values");
	snakeoil_LOAD_ATTR(pkgcore_atom_StrExactMatch, tmp, "StrExactMatch");
	snakeoil_LOAD_ATTR(pkgcore_atom_StrGlobMatch, tmp, "StrGlobMatch");
	snakeoil_LOAD_ATTR(pkgcore_atom_ContainmentMatch, tmp, "ContainmentMatch");
	snakeoil_LOAD_ATTR(pkgcore_atom_ValAnd, tmp, "AndRestriction");
	snakeoil_LOAD_ATTR(pkgcore_atom_ValOr, tmp, "OrRestriction");
	Py_CLEAR(tmp);

	snakeoil_LOAD_SINGLE_ATTR(pkgcore_atom_PackageRestrict, "pkgcore.restrictions.packages",
		"PackageRestriction");

	snakeoil_LOAD_STRING(pkgcore_atom_transitive_use_atom_str, "_transitive_use_atom");
	snakeoil_LOAD_STRING(pkgcore_atom__class__, "__class__");
	snakeoil_LOAD_STRING(pkgcore_atom_cpvstr,		"cpvstr");
	snakeoil_LOAD_STRING(pkgcore_atom_key,		   "key");
	snakeoil_LOAD_STRING(pkgcore_atom_category,	  "category");
	snakeoil_LOAD_STRING(pkgcore_atom_package,	   "package");
	snakeoil_LOAD_STRING(pkgcore_atom_version,	   "version");
	snakeoil_LOAD_STRING(pkgcore_atom_revision,	  "revision");
	snakeoil_LOAD_STRING(pkgcore_atom_fullver,	   "fullver");
	snakeoil_LOAD_STRING(pkgcore_atom_hash,		  "_hash");
	snakeoil_LOAD_STRING(pkgcore_atom_use,		   "use");
	snakeoil_LOAD_STRING(pkgcore_atom_slot,		  "slot");
	snakeoil_LOAD_STRING(pkgcore_atom_repo_id,	   "repo_id");
	snakeoil_LOAD_STRING(pkgcore_atom_restrict_repo_id,
											"repo.repo_id");
	snakeoil_LOAD_STRING(pkgcore_atom_op_glob,	   "=*");
	snakeoil_LOAD_STRING(pkgcore_atom_blocks,		"blocks");
	snakeoil_LOAD_STRING(pkgcore_atom_blocks_strongly,"blocks_strongly");
	snakeoil_LOAD_STRING(pkgcore_atom_op,			"op");
	snakeoil_LOAD_STRING(pkgcore_atom_negate_vers,   "negate_vers");
	snakeoil_LOAD_STRING(pkgcore_atom_restrictions,  "restrictions");

	snakeoil_LOAD_STRING(pkgcore_atom_op_ge,		 ">=");
	snakeoil_LOAD_STRING(pkgcore_atom_op_gt,		 ">");
	snakeoil_LOAD_STRING(pkgcore_atom_op_le,		 "<=");
	snakeoil_LOAD_STRING(pkgcore_atom_op_lt,		 "<");
	snakeoil_LOAD_STRING(pkgcore_atom_op_eq,		 "=");
	snakeoil_LOAD_STRING(pkgcore_atom_op_droprev,	"~");
	snakeoil_LOAD_STRING(pkgcore_atom_op_none,	   "");

	PyObject *d = PyDict_New();
	if(!d)
		return;

	PyObject *overrides = PyDict_New();
	if(!overrides)
		return;

	tmp = PyType_GenericNew(&pkgcore_atom_init_type, NULL, NULL);
	if(!tmp)
		return;
	if(PyDict_SetItemString(overrides, "__init__", tmp))
		return;

	tmp = PyType_GenericNew(&pkgcore_atom_getattr_nondesc_type, NULL, NULL);
	if(!tmp)
		return;
	if(PyDict_SetItemString(overrides, "__getattr__nondesc", tmp))
		return;

	tmp = PyType_GenericNew(&pkgcore_atom_getattr_desc_type, NULL, NULL);
	if(!tmp)
		return;
	if(PyDict_SetItemString(overrides, "__getattr__desc", tmp))
		return;

	PyObject *new_module = Py_InitModule3("_atom", NULL, pkgcore_atom_documentation);
	if (!new_module)
		return;

	PyModule_AddObject(new_module, "overrides", overrides);

	if (PyErr_Occurred()) {
		Py_FatalError("can't initialize module _atom");
	}
}
