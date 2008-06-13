#include "Python.h"

static PyObject *discard, *clear, *add;

static PyObject *
incremental_expansion(PyObject *self, PyObject *args, PyObject *kwargs)
{
	int finalize;
	static char *keywords[] = {
		"orig",
		"iterable",
		"msg_prefix",
		"finalize",
		NULL
	};
	PyObject *orig, *iterable, *finalize_obj = Py_True;
	PyObject *iterator, *item;

	char *msg_prefix = "";
	if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OO|sO", keywords,
		&orig, &iterable, &msg_prefix, &finalize_obj))
		return NULL;

	iterator = PyObject_GetIter(iterable);
	if (iterator == NULL)
		return NULL;

	finalize = finalize_obj ? PyObject_IsTrue(finalize_obj) : 0;
	if (finalize == -1)
		return NULL;
	while ((item = PyIter_Next(iterator))) {
		char *str;
		if (!PyString_CheckExact(item)) {
			PyErr_Format(PyExc_ValueError,
				"iterable should yield strings");
			goto err;
		}
		str = PyString_AS_STRING(item);
		if (*str == '-') {
			str++;
			if (*str == '\0') {
				PyErr_Format(PyExc_ValueError,
				"%sencountered an incomplete negation, '-'",
					msg_prefix);
				goto err;
			}
			if (!strcmp(str, "*")) {
				if (!PyObject_CallMethodObjArgs(orig, clear, NULL))
					goto err;
			} else {
				PyObject *discard = PyString_FromFormat("%s", str);
				if (!PyObject_CallMethod(orig, "discard",
					"(O)", discard))
					goto err;
			}
			if (!finalize) {
				if (!PyObject_CallMethodObjArgs(orig, add, item, NULL))
					goto err;
			}
		} else {
			PyObject *discard = PyString_FromFormat("-%s", str);
			if (!discard ||
			    !PyObject_CallMethod(orig, "discard", "(O)",
					discard) ||
			    !PyObject_CallMethodObjArgs(orig, add, item, NULL))
				goto err;
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
