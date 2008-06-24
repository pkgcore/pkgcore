#include "Python.h"

static PyObject *discard, *clear, *add;

static PyObject *
incremental_expansion(PyObject *self, PyObject *args, PyObject *kwargs)
{
	int finalize = 0;
	static char *keywords[] = {
		"orig",
		"iterable",
		"msg_prefix",
		"finalize",
		NULL
	};
	PyObject *orig, *iterable, *finalize_obj = Py_True;
	PyObject *iterator, *item = NULL;
	PyObject *tmp = NULL;

	char *msg_prefix = "";
	if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OO|sO", keywords,
		&orig, &iterable, &msg_prefix, &finalize_obj))
		return NULL;

	if(NULL == (iterator = PyObject_GetIter(iterable)))
		return NULL;

	if(finalize_obj) {
		finalize = PyObject_IsTrue(finalize_obj);
		if(PyErr_Occurred()) {
			goto err;
		}
	}

	while ((item = PyIter_Next(iterator))) {
		char *str;
		if (!PyString_CheckExact(item)) {
			PyErr_Format(PyExc_ValueError,
				"iterable should yield strings");
			goto err;
		}
		str = PyString_AS_STRING(item);
		if ('-' == *str) {
			str++;
			if ('\0' == *str) {
				PyErr_Format(PyExc_ValueError,
				"%sencountered an incomplete negation, '-'",
					msg_prefix);
				goto err;
			}
			if (!strcmp(str, "*")) {
				if (NULL == (tmp = PyObject_CallMethodObjArgs(orig, clear, NULL)))
					goto err;
				Py_DECREF(tmp);
			} else {
				PyObject *discard;
				if (NULL == (discard = PyString_FromFormat("%s", str))) {
					goto err;
				}
				if (NULL == (tmp = PyObject_CallMethod(orig, "discard",
					"(O)", discard))) {
					Py_DECREF(discard);
					goto err;
				}
				Py_DECREF(tmp);
				Py_DECREF(discard);
			}
			if (!finalize) {
				if (NULL == (tmp = PyObject_CallMethodObjArgs(orig, add, item, NULL)))
					goto err;
				Py_DECREF(tmp);
			}
		} else {
			PyObject *discard;
			if(NULL == (discard = PyString_FromFormat("-%s", str)))
				goto err;
			if(NULL == (tmp = PyObject_CallMethod(orig, "discard",
				"(O)", discard))) {
				Py_DECREF(discard);
				goto err;
			}
			Py_DECREF(tmp);
			if(NULL == (tmp = PyObject_CallMethodObjArgs(orig, add,
				item, NULL))) {
				Py_DECREF(discard);
				goto err;
			}
			Py_DECREF(tmp);
			Py_DECREF(discard);
		}
		Py_DECREF(item);
	}
	Py_DECREF(iterator);
	Py_RETURN_NONE;
err:
	Py_DECREF(iterator);
	Py_DECREF(item); /* item is leaked from the loop */
	return NULL;
}

static PyMethodDef MiscMethods[] = {
	{"incremental_expansion", (PyCFunction)incremental_expansion,
		METH_VARARGS | METH_KEYWORDS, ""},
	{NULL, NULL, 0, NULL}        /* Sentinel */
};

PyMODINIT_FUNC
init_misc(void)
{
	PyObject *m;
#define load_string(name)			\
	name = PyString_FromString(#name);	\
	if (!name)				\
		return
	load_string(discard);
	load_string(add);
	load_string(clear);
	m = Py_InitModule("_misc", MiscMethods);
}
