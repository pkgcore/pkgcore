/*
 * Copyright: 2006 Marien Zwart <marienz@gentoo.org>
 * License: GPL2
 *
 * C version of some of pkgcore (for extra speed).
 */

#include "Python.h"


/* iter_flatten_func: recursively flatten an iterable with a func as filter. */

typedef struct {
	PyObject_HEAD
	PyObject *skip_func;
	PyObject *iterables;
} pkgcore_iter_flatten_func;

static void
pkgcore_iter_flatten_func_dealloc(pkgcore_iter_flatten_func *self)
{
	Py_XDECREF(self->skip_func);
	Py_XDECREF(self->iterables);
	self->ob_type->tp_free((PyObject*) self);
}

static int
pkgcore_iter_flatten_func_init(pkgcore_iter_flatten_func *self,
	PyObject *args, PyObject *kwargs)
{
	PyObject *l=NULL, *skip_func=NULL, *tmp, *iter, *iters;

	if (!PyArg_ParseTuple(args, "OO", &l, &skip_func))
		return -1;

	/* This constructs the initial "iterables" of [iter([l])] */
	tmp = PyList_New(1);
	if (!tmp)
		return -1;

	Py_INCREF(l);
	PyList_SET_ITEM(tmp, 0, l);

	iter = PyObject_GetIter(tmp);
	Py_DECREF(tmp);
	if (!iter)
		return -1;

	iters = PyList_New(1);
	if (!iters) {
		Py_DECREF(iter);
		return -1;
	}
	PyList_SET_ITEM(iters, 0, iter);

	/* Assign stuff to self now */

	tmp = self->iterables;
	self->iterables = iters;
	Py_XDECREF(tmp);

	tmp = self->skip_func;
	Py_INCREF(skip_func);
	self->skip_func = skip_func;
	Py_XDECREF(tmp);

	return 0;
}


static PyObject *
pkgcore_iter_flatten_func_iternext(pkgcore_iter_flatten_func *self)
{
	PyObject *tail, *result, *tmp;
	int n, res;

	/* Look at the final iterator on our stack: */
	if(NULL == self->iterables) {
		printf("called when already went empty\n");
		PyErr_SetString(PyExc_StopIteration, "");
		return NULL;
	}

	while(n = PyList_GET_SIZE(self->iterables)) {
		tail = PySequence_GetItem(self->iterables, n - 1);

		/* See if it has any results left: */

		result = PyIter_Next(tail);
		Py_DECREF(tail);
		if (result) {

			/* See if we need to iterate over this new result: */

			tmp = PyObject_CallFunctionObjArgs(self->skip_func, result, NULL);
			if (!tmp) {
				Py_DECREF(result);
				return NULL;
			}

			res = PyObject_IsTrue(tmp);
			Py_DECREF(tmp);
			if (res < 0) {
				Py_DECREF(result);
				return NULL;
			} else if (res) {
				/* skip_func returned True so return this. */
				return result;
			}

			/* If it is an iterator add it to our chain, else return it. */

			tmp = PyObject_GetIter(result);
			if (tmp) {
				/* Iterable, append to our stack and continue. */
				Py_DECREF(result);
				res = PyList_Append(self->iterables, tmp);
				Py_DECREF(tmp);
				if (res < 0)
					return NULL;
				continue;
			}

			/* If we get here PyObject_GetIter raised an exception.
			 * If it was TypeError we have a non-iterator we can just return.
			 * Else we propagate the error.
			 */

			if (!PyErr_ExceptionMatches(PyExc_TypeError)) {
				Py_DECREF(result);
				return NULL;
			}
			PyErr_Clear();
			return result;
		}

		/* If we get here PyIter_Next did not return an item. */
		if (PyErr_Occurred())
			return NULL;


		/* PyIter_Next returns NULL with no exception for "StopIteration". */
		/* XXX this is an accident waiting to happen: what if
		 * PyIter_Next messed with our iterable length? */

		if (PySequence_DelItem(self->iterables, n - 1) < 0) {
			PyErr_SetString(PyExc_StopIteration, "");
			return NULL;
		}
	}

	PY_DECREF(self->iterables);
	self->iterables = NULL;
	PyErr_SetString(PyExc_StopIteration, "");
	/* We ran out of iterables entirely, so we are done */
	return NULL;
}

static PyTypeObject pkgcore_iter_flatten_func_type = {
	PyObject_HEAD_INIT(NULL)
	0,                         /*ob_size*/
	"_stuff.iter_flatten_func",    /*tp_name*/
	sizeof(pkgcore_iter_flatten_func), /*tp_basicsize*/
	0,                         /*tp_itemsize*/
	(destructor)pkgcore_iter_flatten_func_dealloc, /*tp_dealloc*/
	0,                         /*tp_print*/
	0,                         /*tp_getattr*/
	0,                         /*tp_setattr*/
	0,                         /*tp_compare*/
	0,                         /*tp_repr*/
	0,                         /*tp_as_number*/
	0,                         /*tp_as_sequence*/
	0,                         /*tp_as_mapping*/
	0,                         /*tp_hash */
	(ternaryfunc)0, /*tp_call*/
	(reprfunc)0,		/*tp_str*/
	0,                         /*tp_getattro*/
	0,                         /*tp_setattro*/
	0,                         /*tp_as_buffer*/
	Py_TPFLAGS_DEFAULT,        /*tp_flags*/
	0, /* Documentation string */
	(traverseproc)0,		               /* tp_traverse */
	(inquiry)0,		               /* tp_clear */
	(richcmpfunc)0,		               /* tp_richcompare */
	0,		               /* tp_weaklistoffset */
	(getiterfunc)PyObject_SelfIter,	/* tp_iter */
	(iternextfunc)pkgcore_iter_flatten_func_iternext, /* tp_iternext */
	0,             /* tp_methods */
	0,             /* tp_members */
	0,                         /* tp_getset */
	0,                         /* tp_base */
	0,                         /* tp_dict */
	0,                         /* tp_descr_get */
	0,                         /* tp_descr_set */
	0,                         /* tp_dictoffset */
	(initproc)pkgcore_iter_flatten_func_init, /* tp_init */
	0,                         /* tp_alloc */
	PyType_GenericNew,  /* tp_new */
};

/* iter_flatten_instance: recursively flatten an iterable 
   except for some instances */

typedef struct {
	PyObject_HEAD
	PyObject *skip_flattening;
	PyObject *iterables;
} pkgcore_iter_flatten_instance;


static void
pkgcore_iter_flatten_instance_dealloc(pkgcore_iter_flatten_instance *self)
{
	Py_XDECREF(self->skip_flattening);
	Py_XDECREF(self->iterables);
	self->ob_type->tp_free((PyObject*) self);
}


static int
pkgcore_iter_flatten_instance_init(pkgcore_iter_flatten_instance *self,
	PyObject *args, PyObject *kwargs)
{
	PyObject *l=NULL, *skip_flattening=NULL, *tmp, *iter, *iters;

	if (!PyArg_ParseTuple(args, "OO", &l, &skip_flattening))
		return -1;

	/* This constructs the initial "iterables" of [iter([l])] */

	tmp = PyList_New(1);
	if (!tmp)
		return -1;

	Py_INCREF(l);
	PyList_SET_ITEM(tmp, 0, l);

	iter = PyObject_GetIter(tmp);
	Py_DECREF(tmp);
	if (!iter)
		return -1;

	iters = PyList_New(1);
	if (!iters) {
		Py_DECREF(iter);
		return -1;
	}

	PyList_SET_ITEM(iters, 0, iter);

	/* Assign stuff to self now */

	tmp = self->iterables;
	self->iterables = iters;
	Py_XDECREF(tmp);

	tmp = self->skip_flattening;
	Py_INCREF(skip_flattening);
	self->skip_flattening = skip_flattening;
	Py_XDECREF(tmp);

	return 0;
}

static PyObject *
pkgcore_iter_flatten_instance_iternext(pkgcore_iter_flatten_instance *self)
{

	PyObject *tail, *result, *tmp;
	int n, res;

	/* Look at the final iterator on our stack: */


	if(NULL == self->iterables) {
		printf("called when already went empty\n");
		PyErr_SetString(PyExc_StopIteration, "");
		return NULL;
	}

	while(0 != (n = PyList_GET_SIZE(self->iterables))) {
		printf("n==%i\n", n);
		tail = PySequence_GetItem(self->iterables, n - 1);

		/* See if it has any results left: */

		result = PyIter_Next(tail);
		Py_DECREF(tail);
		if (result) {
			/* See if we need to iterate over this new result: */

			res = PyObject_IsInstance(result, self->skip_flattening);
			if (res < 0) {
				Py_DECREF(result);
				return NULL;
			}
			if (res)
				/* In skip_flattening so return this. */
				return result;

			/* If it is an iterator add it to our chain, else return it. */
			tmp = PyObject_GetIter(result);
			if (tmp) {
				/* Iterable, append to our stack and continue. */
				Py_DECREF(result);
				res = PyList_Append(self->iterables, tmp);
				Py_DECREF(tmp);
				if (res < 0)
					return NULL;
				continue;
			}
			/* If we get here PyObject_GetIter raised an exception.
			 * If it was TypeError we have a non-iterator we can just return.
			 * Else we propagate the error.
			 */
			if (!PyErr_ExceptionMatches(PyExc_TypeError)) {
				Py_DECREF(result);
				return NULL;
			}
			PyErr_Clear();
			return result;
		}
		/* If we get here PyIter_Next did not return an item. */
		if (PyErr_Occurred())
			return NULL;
		/* PyIter_Next returns NULL with no exception for "StopIteration". */

		/* XXX this is an accident waiting to happen: what if
		 * PyIter_Next messed with our iterable length? */
		if (PySequence_DelItem(self->iterables, n - 1) < 0) {
			PyErr_SetString(PyExc_StopIteration, "");
			return NULL;
		}
	}
	printf("n==%i\n", n);

	/* We ran out of iterables entirely, so we are done */
	PY_DECREF(self->iterables);
	self->iterables = NULL;
	PyErr_SetString(PyExc_StopIteration, "");
	return NULL;
}

static PyTypeObject pkgcore_iter_flatten_instance_type = {
	PyObject_HEAD_INIT(NULL)
	0,                         /*ob_size*/
	"_stuff.iter_flatten_instance",    /*tp_name*/
	sizeof(pkgcore_iter_flatten_instance), /*tp_basicsize*/
	0,                         /*tp_itemsize*/
	(destructor)pkgcore_iter_flatten_instance_dealloc, /*tp_dealloc*/
	0,                         /*tp_print*/
	0,                         /*tp_getattr*/
	0,                         /*tp_setattr*/
	0,                         /*tp_compare*/
	0,                         /*tp_repr*/
	0,                         /*tp_as_number*/
	0,                         /*tp_as_sequence*/
	0,                         /*tp_as_mapping*/
	0,                         /*tp_hash */
	(ternaryfunc)0, /*tp_call*/
	(reprfunc)0,		/*tp_str*/
	0,                         /*tp_getattro*/
	0,                         /*tp_setattro*/
	0,                         /*tp_as_buffer*/
	Py_TPFLAGS_DEFAULT,        /*tp_flags*/
	0, /* Documentation string */
	(traverseproc)0,		               /* tp_traverse */
	(inquiry)0,		               /* tp_clear */
	(richcmpfunc)0,		               /* tp_richcompare */
	0,		               /* tp_weaklistoffset */
	(getiterfunc)PyObject_SelfIter,	/* tp_iter */
	(iternextfunc)pkgcore_iter_flatten_instance_iternext, /* tp_iternext */
	0,             /* tp_methods */
	0,             /* tp_members */
	0,                         /* tp_getset */
	0,                         /* tp_base */
	0,                         /* tp_dict */
	0,                         /* tp_descr_get */
	0,                         /* tp_descr_set */
	0,                         /* tp_dictoffset */
	(initproc)pkgcore_iter_flatten_instance_init, /* tp_init */
	0,                         /* tp_alloc */
	PyType_GenericNew,  /* tp_new */
};


/* Module initialization */

/* Static tuple storing the default value of skip_flattening. */
static PyObject *iter_flatten_default_instance = NULL;


static PyObject *
pkgcore_iter_flatten(PyObject *self, PyObject *args, PyObject *kwargs)
{
	
	PyObject *l, *skip_flattening=NULL, *skip_func=NULL;
	
	static char *kwlist[] = {"l", "skip_flattening", "skip_func", NULL};

	if (!PyArg_ParseTupleAndKeywords(args, kwargs, "O|OO", kwlist,
		&l, &skip_flattening, &skip_func))
		return NULL;

	if (skip_func) {
		if (skip_flattening) {
			PyErr_SetString(PyExc_TypeError,
				"Cannot set both skip_flattening and skip_func");
			return NULL;
		}
		return PyObject_CallFunctionObjArgs(
			(PyObject*)&pkgcore_iter_flatten_func_type, l, skip_func, NULL);
	}

	if (!skip_flattening)
		skip_flattening = iter_flatten_default_instance;

	return PyObject_CallFunctionObjArgs(
		(PyObject*)&pkgcore_iter_flatten_instance_type,
		l, skip_flattening, NULL);
}


static struct PyMethodDef pkgcore_lists_methods[] = {
	{"iter_flatten", (PyCFunction)pkgcore_iter_flatten, METH_VARARGS|METH_KEYWORDS, "iter_flatten stuff"},
	{NULL,	 (PyCFunction)NULL, 0, NULL}		/* sentinel */
};


/* Initialization function for the module */

static char pkgcore_lists_documentation[] = "C version of some of pkgcore.";

PyMODINIT_FUNC
init_lists()
{
	PyObject *m;

	if (PyType_Ready(&pkgcore_iter_flatten_func_type) < 0)
		return;

	if (PyType_Ready(&pkgcore_iter_flatten_instance_type) < 0)
		return;

	iter_flatten_default_instance = PyTuple_Pack(1, &PyBaseString_Type);
	if (!iter_flatten_default_instance)
		return;

	/* Create the module and add the functions */
	m = Py_InitModule3("_lists", pkgcore_lists_methods,
		pkgcore_lists_documentation);

	/* Check for errors */
	if (PyErr_Occurred())
		Py_FatalError("can't initialize module _lists");
}
