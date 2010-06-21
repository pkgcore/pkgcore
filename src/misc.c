#include "Python.h"

static PyObject *discard_str, *clear_str, *add_str;


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
	PyObject *orig, *iterable, *finalize_obj = NULL;
	PyObject *iterator, *item = NULL;
	PyObject *tmp_ret = NULL;
	int is_set;

	char *msg_prefix = "";
	if (!PyArg_ParseTupleAndKeywords(args, kwargs, "OO|sO", keywords,
		&orig, &iterable, &msg_prefix, &finalize_obj))
		return NULL;

	is_set = PySet_Check(orig);
	if(finalize_obj) {
		finalize = PyObject_IsTrue(finalize_obj);
		if(-1 == finalize) {
			return NULL;
		}
	} else {
		finalize = 1;
	}


	if(NULL == (iterator = PyObject_GetIter(iterable)))
		return NULL;

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
			if ('*' == *str && '\0' == str[1]) {
				if(is_set) {
					if(-1 == PySet_Clear(orig)) {
						goto err;
					}
				} else {
					if (NULL == (tmp_ret = PyObject_CallMethodObjArgs(orig, clear_str, NULL))) {
						goto err;
					}
					Py_DECREF(tmp_ret);
				}
			} else {
				PyObject *discard_val;
				if (NULL == (discard_val = PyString_FromString(str))) {
					goto err;
				}
				if(is_set) {
					if(-1 == PySet_Discard(orig, discard_val)) {
						Py_DECREF(discard_val);
						goto err;
					}
					Py_DECREF(discard_val);
				} else {
					tmp_ret = PyObject_CallMethodObjArgs(orig, discard_str, discard_val, NULL);
					Py_DECREF(discard_val);
					if(!tmp_ret) {
						goto err;
					}
					Py_DECREF(tmp_ret);
				}
			}
			if (!finalize) {
				if(is_set) {
					if(-1 == PySet_Add(orig, item)) {
						goto err;
					}
				} else {
					if (NULL == (tmp_ret = PyObject_CallMethodObjArgs(orig, add_str, item, NULL)))
						goto err;
					Py_DECREF(tmp_ret);
				}
			}
		} else {
			Py_ssize_t len = strlen(str);
			// note that this auto sets a trailing newline.
			PyObject *discard_val = PyString_FromStringAndSize(NULL, len + 1);
			if(!discard_val)
				goto err;
			char *p = PyString_AS_STRING(discard_val);
			p[0] = '-';
			Py_MEMCPY(p + 1, str, len + 1);

			if(is_set) {
				if(-1 == PySet_Discard(orig, discard_val)) {
					Py_DECREF(discard_val);
					goto err;
				}
				Py_DECREF(discard_val);
			} else {
				tmp_ret = PyObject_CallMethodObjArgs(orig, discard_str, discard_val, NULL);
				Py_DECREF(discard_val);
				if(!tmp_ret)
					goto err;
				Py_DECREF(tmp_ret);
			}
			if(NULL == (tmp_ret = PyObject_CallMethodObjArgs(orig, add_str,
				item, NULL))) {
				goto err;
			}
			Py_DECREF(tmp_ret);
		}
		Py_DECREF(item);
	}
	Py_DECREF(iterator);
	Py_RETURN_NONE;
err:
	Py_XDECREF(iterator);
	Py_XDECREF(item); /* item is leaked from the loop */
	return NULL;
}

static PyMethodDef MiscMethods[] = {
	{"incremental_expansion", (PyCFunction)incremental_expansion,
		METH_VARARGS | METH_KEYWORDS, ""},
	{NULL, NULL, 0, NULL}		/* Sentinel */
};

PyMODINIT_FUNC
init_misc(void)
{
	PyObject *m;
#define load_string(val, name)			\
	name = PyString_FromString(val);	\
	if (!name)				\
		return			  \
	PyString_InternInPlace(&name);

	load_string("discard", discard_str);
	load_string("add", add_str);
	load_string("clear", clear_str);
	m = Py_InitModule("_misc", MiscMethods);
}
