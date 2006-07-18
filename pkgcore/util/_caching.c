/*
 * Copyright: 2006 Marien Zwart <marienz@gentoo.org>
 * License: GPL2
 *
 * C version of some of pkgcore (for extra speed).
 */

#include "Python.h"


/*
 * WeakValFinalizer: holds a reference to a dict and key,
 * does "del dict[key]" when called. Used as weakref callback.
 * Only used internally (does not expose a constructor/new method).
 */

typedef struct {
	PyObject_HEAD
	PyObject *dict;
	PyObject *key;
} pkgcore_WeakValFinalizer;

static void
pkgcore_WeakValFinalizer_dealloc(pkgcore_WeakValFinalizer *self)
{
	Py_CLEAR(self->dict);
	Py_CLEAR(self->key);
	self->ob_type->tp_free((PyObject*) self);
}

static PyObject *
pkgcore_WeakValFinalizer_call(pkgcore_WeakValFinalizer *self,
							  PyObject *args, PyObject *kwargs)
{
	/* We completely ignore whatever arguments are passed to us
	   (should be a single positional (the weakref) we do not need). */
	if (PyObject_DelItem(self->dict, self->key) < 0)
		return NULL;
	Py_RETURN_NONE;
}

static PyTypeObject pkgcore_WeakValFinalizerType = {
    PyObject_HEAD_INIT(NULL)
    0,                         /*ob_size*/
    "_pkgcore.WeakValFinalizer",    /*tp_name*/
    sizeof(pkgcore_WeakValFinalizer), /*tp_basicsize*/
    0,                         /*tp_itemsize*/
    (destructor)pkgcore_WeakValFinalizer_dealloc, /*tp_dealloc*/
    0,                         /*tp_print*/
    0,                         /*tp_getattr*/
    0,                         /*tp_setattr*/
    0,                         /*tp_compare*/
    0,                         /*tp_repr*/
    0,                         /*tp_as_number*/
    0,                         /*tp_as_sequence*/
    0,                         /*tp_as_mapping*/
    0,                         /*tp_hash */
    (ternaryfunc)pkgcore_WeakValFinalizer_call, /*tp_call*/
	(reprfunc)0,		/*tp_str*/
    0,                         /*tp_getattro*/
    0,                         /*tp_setattro*/
    0,                         /*tp_as_buffer*/
    Py_TPFLAGS_DEFAULT,        /*tp_flags*/
};

/* WeakInstMeta: metaclass for instance caching. */

typedef struct {
	PyTypeObject type;
	PyObject *inst_dict;
	int inst_caching;
} pkgcore_WeakInstMeta;

static void
pkgcore_WeakInstMeta_dealloc(pkgcore_WeakInstMeta* self)
{
	Py_CLEAR(self->inst_dict);
	PyType_Type.tp_dealloc((PyObject*)self);
}

static PyTypeObject pkgcore_WeakInstMetaType;

static PyObject *
pkgcore_WeakInstMeta_new(PyTypeObject *type, PyObject *args, PyObject *kwargs)
{
	const char *name;
	PyTupleObject *bases;
	PyObject *d;
	int inst_caching = 0;
	static char *kwlist[] = {"name", "bases", "dict", 0};

	if (!PyArg_ParseTupleAndKeywords(args, kwargs, "sO!O!", kwlist,
									 &name,
									 &PyTuple_Type, &bases,
									 &PyDict_Type, &d))
		return NULL;

	PyObject *cachesetting = PyMapping_GetItemString(d, "__inst_caching__");
	if (cachesetting) {
		inst_caching = PyObject_IsTrue(cachesetting);
		Py_DECREF(cachesetting);
		if (inst_caching < 0)
			return NULL;
	} else {
		if (!PyErr_ExceptionMatches(PyExc_KeyError))
			return NULL;
		PyErr_Clear();
	}
	if (PyMapping_SetItemString(d, "__inst_caching__",
								inst_caching ? Py_True : Py_False) < 0)
		return NULL;

	if (inst_caching) {
		PyObject *slots = PyMapping_GetItemString(d, "__slots__");
		if (slots) {
			int has_weakref = 0;
			PyObject *base;
			int i, n = PyTuple_GET_SIZE(bases);
			for (i = 0; i < n; i++) {
				base = PyTuple_GET_ITEM(bases, i);
				if (PyObject_HasAttrString(base, "__weakref__")) {
					has_weakref = 1;
					break;
				}
			}
			if (!has_weakref) {
				PyObject *slottuple = Py_BuildValue("(s)", "__weakref__");
				if (!slottuple) {
					Py_DECREF(slots);
					return NULL;
				}
				PyObject *newslots = PySequence_Concat(slots, slottuple);
				Py_DECREF(slottuple);
				if (!newslots)
					return NULL;
				if (PyMapping_SetItemString(d, "__slots__", newslots) < 0) {
					Py_DECREF(newslots);
					Py_DECREF(slots);
					return NULL;
				}
				Py_DECREF(newslots);
			}
			Py_DECREF(slots);
		} else {
			if (!PyErr_ExceptionMatches(PyExc_KeyError))
				return NULL;
			PyErr_Clear();
		}
	}

	pkgcore_WeakInstMeta *self;
	self = (pkgcore_WeakInstMeta*)PyType_Type.tp_new(type, args, kwargs);
	if (!self)
		return NULL;

	self->inst_caching = inst_caching;

	if (inst_caching) {
		if (!(self->inst_dict = PyDict_New())) {
			Py_DECREF((PyObject*)self);
			return NULL;
		}
	}
	return (PyObject*) self;
}


static PyObject *
pkgcore_WeakInstMeta_call(pkgcore_WeakInstMeta *self,
						  PyObject *args, PyObject *kwargs)
{
	PyObject *key, *kwlist, *kwtuple, *resobj = NULL;
	int result;
	if (!self->inst_caching)
		/* No caching, just do what a "normal" type does */
		return PyType_Type.tp_call((PyObject*)self, args, kwargs);

	if (kwargs) {
		/* If disable_inst_caching=True is passed pop it and disable caching */
		PyObject *obj = PyMapping_GetItemString(kwargs,
												"disable_inst_caching");
		if (obj) {
			result = PyObject_IsTrue(obj);
			Py_DECREF(obj);
			if (result < 0)
				return NULL;

			if (PyMapping_DelItemString(kwargs, "disable_inst_caching") < 0)
				return NULL;

			if (result)
				return PyType_Type.tp_call((PyObject*)self, args, kwargs);
		} else {
			if (!PyErr_ExceptionMatches(PyExc_KeyError))
				return NULL;
			PyErr_Clear();
		}
		/* Convert kwargs to a sorted tuple so we can hash it. */
		if (!(kwlist = PyMapping_Items(kwargs)))
			return NULL;

		if (PyList_Sort(kwlist) < 0) {
			Py_DECREF(kwlist);
			return NULL;
		}

		kwtuple = PyList_AsTuple(kwlist);
		Py_DECREF(kwlist);
		if (!kwtuple)
			return NULL;
	} else {
		/* null kwargs is equivalent to a zero-length tuple */
		kwtuple = PyTuple_New(0);
		if (!kwtuple)
			return NULL;
	}

	/* Construct the dict key. Be careful not to leak this below! */
	key = PyTuple_Pack(2, args, kwtuple);
	Py_DECREF(kwtuple);
	if (!key)
		return NULL;

	resobj = PyObject_GetItem(self->inst_dict, key);
	if (resobj) {
		/* We have a weakref cached, return the value if it is still there */
		PyObject *actual = PyWeakref_GetObject(resobj);
		Py_DECREF(resobj);
		if (!actual) {
			Py_DECREF(key);
			return NULL;
		}
		if (actual != Py_None) {
			Py_INCREF(actual);
			Py_DECREF(key);
			return actual;
		}
		/* PyWeakref_GetObject returns a borrowed reference, do not clear it */
	} else {
		/* Check and warn if GetItem failed because the key is unhashable */
		if (PyErr_ExceptionMatches(PyExc_TypeError) ||
			PyErr_ExceptionMatches(PyExc_NotImplementedError)) {
			PyErr_Clear();
			PyObject *format, *formatargs, *message;
			if (format = PyString_FromString(
					"caching for %s, key=%s is unhashable")) {
				if (formatargs = PyTuple_Pack(2, self, key)) {
					if (message = PyString_Format(format, formatargs)) {
						PyErr_Warn(NULL, PyString_AsString(message));
						resobj = PyType_Type.tp_call((PyObject*)self,
													 args, kwargs);
						Py_DECREF(message);
					}
					Py_DECREF(formatargs);
				}
				Py_DECREF(format);
			}
			Py_DECREF(key);
			return resobj;
		} else if (!PyErr_ExceptionMatches(PyExc_KeyError)) {
			Py_DECREF(key);
			return NULL;
		}
		PyErr_Clear();
	}
	/* If we get here it was not cached but should be */

	resobj = PyType_Type.tp_call((PyObject*)self, args, kwargs);
	if (!resobj) {
		Py_DECREF(key);
		return NULL;
	}

	pkgcore_WeakValFinalizer *finalizer = PyObject_New(
		pkgcore_WeakValFinalizer, &pkgcore_WeakValFinalizerType);
	if (!finalizer) {
		Py_DECREF(key);
		Py_DECREF(resobj);
		return NULL;
	}
	Py_INCREF(self->inst_dict);
	finalizer->dict = self->inst_dict;
	Py_INCREF(key);
	finalizer->key = key;

	PyObject *weakref = PyWeakref_NewRef(resobj, (PyObject*)finalizer);
	Py_DECREF(finalizer);
	if (!weakref) {
		Py_DECREF(key);
		Py_DECREF(resobj);
		return NULL;
	}

	result = PyObject_SetItem(self->inst_dict, key, weakref);
	Py_DECREF(key);
	Py_DECREF(weakref);
	if (result < 0) {
		Py_DECREF(resobj);
		return NULL;
	}
	return resobj;
}


static char pkgcore_WeakInstMetaType__doc__[] = 
	"metaclass for instance caching, resulting in reuse of unique instances";

static PyTypeObject pkgcore_WeakInstMetaType = {
	PyObject_HEAD_INIT(&PyType_Type)
	0,				/*ob_size*/
	"pkgcore.util._caching.WeakInstMeta",			/*tp_name*/
	/* XXX The next line can't be right.
	   I am pretty sure it should be sizeof(pkgcore_WeakInstMeta) but that
	   segfaults. "0" works but I suspect I'm writing to memory I should not
	   somewhere. */
	0 /*sizeof(pkgcore_WeakInstMeta)*/,		/*tp_basicsize*/
	0,				/*tp_itemsize*/
	/* methods */
	(destructor)pkgcore_WeakInstMeta_dealloc,	/*tp_dealloc*/
	(printfunc)0,		/*tp_print*/
	(getattrfunc)0,	/*tp_getattr*/
	(setattrfunc)0,	/*tp_setattr*/
	(cmpfunc)0,		/*tp_compare*/
	(reprfunc)0,		/*tp_repr*/
	0,			/*tp_as_number*/
	0,		/*tp_as_sequence*/
	0,		/*tp_as_mapping*/
	(hashfunc)0,		/*tp_hash*/
	(ternaryfunc)pkgcore_WeakInstMeta_call,		/*tp_call*/
	(reprfunc)0,		/*tp_str*/
    0,                         /*tp_getattro*/
    0,                         /*tp_setattro*/
    0,                         /*tp_as_buffer*/
    Py_TPFLAGS_DEFAULT,        /*tp_flags*/
	pkgcore_WeakInstMetaType__doc__, /* Documentation string */
	(traverseproc)0,		               /* tp_traverse */
    (inquiry)0,		               /* tp_clear */
    (richcmpfunc)0,		               /* tp_richcompare */
    0,		               /* tp_weaklistoffset */
    (getiterfunc)0,		               /* tp_iter */
    (iternextfunc)0,		               /* tp_iternext */
    0,             /* tp_methods */
    0,             /* tp_members */
    0,                         /* tp_getset */
    &PyType_Type,                         /* tp_base */
    0,                         /* tp_dict */
    0,                         /* tp_descr_get */
    0,                         /* tp_descr_set */
    0,                         /* tp_dictoffset */
    (initproc)0,      /* tp_init */
    0,                         /* tp_alloc */
    pkgcore_WeakInstMeta_new,  /* tp_new */
};



/* Module initialization */

static struct PyMethodDef pkgcore_methods[] = {
	{NULL,	 (PyCFunction)NULL, 0, NULL}		/* sentinel */
};


/* Initialization function for the module (*must* be called init_pkgcore) */

static char pkgcore_module_documentation[] =
	"C version of some of pkgcore.";

void
init_caching()
{
	PyObject *m;

    if (PyType_Ready(&pkgcore_WeakInstMetaType) < 0)
        return;

	if (PyType_Ready(&pkgcore_WeakValFinalizerType) < 0)
		return;

	/* Create the module and add the functions */
	m = Py_InitModule3("_caching", pkgcore_methods,
					   pkgcore_module_documentation);

	Py_INCREF(&pkgcore_WeakInstMetaType);
	PyModule_AddObject(m, "WeakInstMeta",
					   (PyObject *)&pkgcore_WeakInstMetaType);

	/* Check for errors */
	if (PyErr_Occurred())
		Py_FatalError("can't initialize module _caching");
}
