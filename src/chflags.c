/*
 * Original author: Stephen Bennett <spb@gentoo.org>
 * Modified by Marien Zwart <marienz@gentoo.org>
 */

#include <Python.h>

#include <sys/stat.h>

static const unsigned long problemflags = 0x00160016;

static PyObject *
chflags_lchflags(PyObject *self, PyObject *args)
{
    char *path = NULL;
    int flags;
    int res;

    if (!PyArg_ParseTuple(args, "eti:lchflags",
                          Py_FileSystemDefaultEncoding, &path, &flags)) {
        return NULL;
    }

    res = lchflags(path, flags);

    PyMem_Free(path);

    if (res < 0) {
        return PyErr_SetFromErrno(PyExc_OSError);
    }

    return PyInt_FromLong((long)res);
}

static PyObject *
chflags_lhasproblems(PyObject *self, PyObject *args)
{
    char *path = NULL;
    struct stat sb;
    int res;

    if (!PyArg_ParseTuple(args, "et:lhasproblems",
                          Py_FileSystemDefaultEncoding, &path)) {
        return NULL;
    }

    res = lstat(path, &sb);

    PyMem_Free(path);

    if (res < 0) {
        return PyErr_SetFromErrno(PyExc_OSError);
    }

    return PyBool_FromLong(sb.st_flags & problemflags);
}

static PyObject *
chflags_lgetflags(PyObject *self, PyObject *args)
{
    char *path = NULL;
    struct stat sb;
    int res;

    if (!PyArg_ParseTuple(args, "et:lgetflags",
                          Py_FileSystemDefaultEncoding, &path)) {
        return NULL;
    }

    res = lstat(path, &sb);

    PyMem_Free(path);

    if (res < 0) {
        return PyErr_SetFromErrno(PyExc_OSError);
    }

    return PyInt_FromLong((long)sb.st_flags);
}

PyDoc_STRVAR(
    chflags_lchflags__doc__,
    "lchflags(path, flags) -> None\n\
Change the flags on path to equal flags.");

PyDoc_STRVAR(
    chflags_lgetflags__doc__,
    "lgetflags(path) -> Integer\n\
Returns the file flags on path.");

PyDoc_STRVAR(
    chflags_lhasproblems__doc__,
    "lhasproblems(path) -> Integer\n\
Returns True if path has any flags set that prevent write operations;\n\
False otherwise.");

static PyMethodDef chflags_methods[] = {
    {"lchflags", chflags_lchflags, METH_VARARGS, chflags_lchflags__doc__},
    {"lgetflags", chflags_lgetflags, METH_VARARGS, chflags_lgetflags__doc__},
    {"lhasproblems", chflags_lhasproblems, METH_VARARGS,
     chflags_lhasproblems__doc__},
    {NULL}
};

PyDoc_STRVAR(
    chflags__doc__,
    "Provide some operations for manipulating FreeBSD's filesystem flags");

PyMODINIT_FUNC
init_chflags()
{
    PyObject *m = Py_InitModule3("chflags", chflags_methods, chflags__doc__);
    if (!m)
        return;

#define addconst(name, value) \
    if (PyModule_AddIntConstant(m, (name), (value)) == -1) \
        return;

    addconst("UF_SETTABLE",  UF_SETTABLE);
    addconst("UF_NODUMP",    UF_NODUMP);
    addconst("UF_IMMUTABLE", UF_IMMUTABLE);
    addconst("UF_APPEND",    UF_APPEND);
    addconst("UF_OPAQUE",    UF_OPAQUE);
    addconst("UF_NOUNLINK",  UF_NOUNLINK);

    addconst("SF_SETTABLE",  SF_SETTABLE);
    addconst("SF_NODUMP",    SF_NODUMP);
    addconst("SF_IMMUTABLE", SF_IMMUTABLE);
    addconst("SF_APPEND",    SF_APPEND);
    addconst("SF_OPAQUE",    SF_OPAQUE);
    addconst("SF_NOUNLINK",  SF_NOUNLINK);
    addconst("SF_SNAPSHOT",  SF_SNAPSHOT);

    addconst("PROBLEM_FLAGS", problemflags);
}
