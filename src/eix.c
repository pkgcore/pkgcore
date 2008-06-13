#include <Python.h>

/*
 * Some of this is fugly. This is because we don't want to backtrack at all.
 * It seems like a corner case, but when this func is being called *millions*
 * of times, it adds up.
 */
#define safe_read() (((ret = fread(&c, 1, 1, f)) == EOF) || ret == 0)

static PyObject *pynumber(PyObject *self, PyObject *args)
{
	unsigned char c;
	int ret, n = 0, num = 0;
	PyObject *pyf;
	FILE *f;

	if (!PyArg_ParseTuple(args, "O", &pyf))
		return NULL;
	if (!PyFile_Check(pyf)) {
		PyErr_SetString(PyExc_ValueError, "Need a file");
		return NULL;
	}

	f = PyFile_AsFile(pyf);

	while (1) {
		if (safe_read())
			goto out;
		if (c == 0xFF)
			n++;
		else
			break;
	}

	if (n && c == 0x00) {
		num = 0xFF;
		n -= 2;
		/* Only read if we're expecting more chars */
		if (n >= 0 && safe_read())
			goto out;
	}

	n++;

	while (n--) {
		num = num << 8;
		num += c;
		if (n && safe_read())
			goto out;
	}

	goto ret;
out:
	if (feof(f)) {
		PyErr_SetString(PyExc_ValueError, "Filehandle closed unexpectedly");
		return NULL;
	}
ret:
	if (ferror(f)) {
		PyObject *s = PyFile_Name(pyf);
		PyErr_SetFromErrnoWithFilename(PyExc_IOError, PyString_AS_STRING(s));
		Py_DECREF(s);
		return NULL;
	}
	return Py_BuildValue("i", num);
}

static PyMethodDef pkgcore_eix_methods[] = {
	{"number", (PyCFunction)pynumber, METH_VARARGS,
		"initialize a depset instance"},
	{NULL}
};

PyMODINIT_FUNC
init_eix()
{
	Py_InitModule3("_eix", pkgcore_eix_methods, NULL);
}
