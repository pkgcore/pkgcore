/*
 * Copyright: 2006 Brian Harring <ferringb@gmail.com>
 * Copyright: 2006-2007 Marien Zwart <marienz@gentoo.org>
 * License: GPL2
 *
 * C version of some of pkgcore (for extra speed).
 */

/* This does not really do anything since we do not use the "#"
 * specifier in a PyArg_Parse or similar call, but hey, not using it
 * means we are Py_ssize_t-clean too!
 */

#define PY_SSIZE_T_CLEAN

#include "Python.h"

/* Compatibility with python < 2.5 */

#if PY_VERSION_HEX < 0x02050000
typedef int Py_ssize_t;
#define PY_SSIZE_T_MAX INT_MAX
#define PY_SSIZE_T_MIN INT_MIN
#endif

#include <dirent.h>
#include <sys/stat.h>


static PyObject *pkgcore_DIRSTR,
    *pkgcore_CHRSTR,
    *pkgcore_BLKSTR,
    *pkgcore_REGSTR,
    *pkgcore_FIFOSTR,
    *pkgcore_LNKSTR,
    *pkgcore_SOCKSTR,
    *pkgcore_UNKNOWNSTR;

/* This function does the actual work for listdir_files and listdir_dirs. */

static PyObject*
pkgcore_readdir_actual_listdir(const char* path, int followsyms,
    int dkind, int skind)
{
    DIR *the_dir;
    struct dirent *entry;

    PyObject *string;

    int pathlen = strlen(path);

    PyObject *result = PyList_New(0);
    if (!result) {
        return NULL;
    }
    if (!(the_dir = opendir(path))) {
        return PyErr_SetFromErrno(PyExc_OSError);
    }
    errno = 0;
    while ((entry = readdir(the_dir))) {
        const char *name = entry->d_name;
        /* skip over "." and ".." */
        if (name[0] == '.' && (name[1] == 0 || (name[1] == '.' &&
            name[2] == 0))) {
            continue;
        }
        if (entry->d_type == DT_UNKNOWN ||
            (followsyms && entry->d_type == DT_LNK)) {

            /* both path components, the "/", the trailing null */

            size_t size = pathlen + strlen(name) + 2;
            char *buffer = (char *) malloc(size);
            if (!buffer) {
                Py_DECREF(result);
                return PyErr_NoMemory();
            }
            snprintf(buffer, size, "%s/%s", path, name);

            struct stat st;
            int ret;
            if (followsyms) {
                ret = stat(buffer, &st);
            } else {
                ret = lstat(buffer, &st);
            }
            free(buffer);
            if (ret != 0) {
                if (followsyms && errno == ENOENT) {
                    /* hit a dangling symlimk; skip. */
                    errno = 0;
                    continue;
                }
                Py_DECREF(result);
                result = NULL;
                break;
            }

            if ((st.st_mode & S_IFMT) != skind) {
                continue;
            }
        } else if (entry->d_type != dkind) {
            continue;
        }
        if (!(string = PyString_FromString(name))) {
            Py_DECREF(result);
            result = NULL;
            break;
        }
        if (PyList_Append(result, string) == -1) {
            Py_DECREF(string);
            Py_DECREF(result);
            result = NULL;
            break;
        }
        Py_DECREF(string);
    }
    closedir(the_dir);
    if (errno) {
        return PyErr_SetFromErrno(PyExc_OSError);
    }
    return result;
}

static PyObject*
pkgcore_readdir_listdir_dirs(PyObject* self, PyObject* args)
{
    char *path;
    PyObject *follow_symlinks_obj = Py_True;

    if (!PyArg_ParseTuple(args, "s|O", &path, &follow_symlinks_obj)) {
        return NULL;
    }

    int follow_symlinks = PyObject_IsTrue(follow_symlinks_obj);
    if (follow_symlinks == -1) {
        return NULL;
    }

    return pkgcore_readdir_actual_listdir(path, follow_symlinks,
        DT_DIR, S_IFDIR);
}

static PyObject*
pkgcore_readdir_listdir_files(PyObject* self, PyObject* args)
{
    char *path;
    PyObject *follow_symlinks_obj = Py_True;

    if (!PyArg_ParseTuple(args, "s|O", &path, &follow_symlinks_obj)) {
        return NULL;
    }

    int follow_symlinks = PyObject_IsTrue(follow_symlinks_obj);
    if (follow_symlinks == -1) {
        return NULL;
    }

    return pkgcore_readdir_actual_listdir(path, follow_symlinks,
        DT_REG, S_IFREG);
}

static PyObject*
pkgcore_readdir_listdir(PyObject* self, PyObject* args)
{
    char *path;

    if (!PyArg_ParseTuple(args, "s", &path)) {
        return NULL;
    }

    PyObject *result = PyList_New(0);
    if (!result) {
        return NULL;
    }

    DIR *the_dir = opendir(path);
    if (!the_dir) {
        return PyErr_SetFromErrno(PyExc_OSError);
    }
    errno = 0;
    struct dirent *entry;
    while ((entry = readdir(the_dir))) {
        const char *name = entry->d_name;
        /* skip over "." and ".." */
        if (!(name[0] == '.' && (name[1] == 0 ||
            (name[1] == '.' && name[2] == 0)))) {

            PyObject *string = PyString_FromString(name);
            if (!string) {
                Py_DECREF(result);
                result = NULL;
                break;
            }
            int res = PyList_Append(result, string);
            Py_DECREF(string);
            if (res == -1) {
                Py_DECREF(result);
                result = NULL;
                break;
            }
        }
    }
    closedir(the_dir);
    if (errno) {
        return PyErr_SetFromErrno(PyExc_OSError);
    }
    return result;
}

static PyObject*
pkgcore_readdir_read_dir(PyObject* self, PyObject* args)
{
    char *path;

    if (!PyArg_ParseTuple(args, "s", &path)) {
        return NULL;
    }
    ssize_t pathlen = strlen(path);

    PyObject *result = PyList_New(0);
    if (!result) {
        return NULL;
    }

    DIR *the_dir = opendir(path);
    if (!the_dir) {
        return PyErr_SetFromErrno(PyExc_OSError);
    }

    struct dirent *entry;
    while ((entry = readdir(the_dir))) {
        const char *name = entry->d_name;
        /* skip over "." and ".." */
        if (name[0] == '.' && (name[1] == 0 ||
            (name[1] == '.' && name[2] == 0))) {
            continue;
        }

        PyObject *typestr;
        switch (entry->d_type) {
            case DT_REG:
                typestr = pkgcore_REGSTR;
                break;
            case DT_DIR:
                typestr = pkgcore_DIRSTR;
                break;
            case DT_FIFO:
                typestr = pkgcore_FIFOSTR;
                break;
            case DT_SOCK:
                typestr = pkgcore_SOCKSTR;
                break;
            case DT_CHR:
                typestr = pkgcore_CHRSTR;
                break;
            case DT_BLK:
                typestr = pkgcore_BLKSTR;
                break;
            case DT_LNK:
                typestr = pkgcore_LNKSTR;
                break;
            case DT_UNKNOWN:
            {
                /* both path components, the "/", the trailing null */
                size_t size = pathlen + strlen(name) + 2;
                char *buffer = (char *) malloc(size);
                if (!buffer) {
                    closedir(the_dir);
                    return PyErr_NoMemory();
                }
                snprintf(buffer, size, "%s/%s", path, name);
                struct stat st;
                int ret = lstat(buffer, &st);
                free(buffer);
                if (ret == -1) {
                    closedir(the_dir);
                    return PyErr_SetFromErrno(PyExc_OSError);
                }
                switch (st.st_mode & S_IFMT) {
                    case S_IFDIR:
                        typestr = pkgcore_DIRSTR;
                        break;
                    case S_IFCHR:
                        typestr = pkgcore_CHRSTR;
                        break;
                    case S_IFBLK:
                        typestr = pkgcore_BLKSTR;
                        break;
                    case S_IFREG:
                        typestr = pkgcore_REGSTR;
                        break;
                    case S_IFLNK:
                        typestr = pkgcore_LNKSTR;
                        break;
                    case S_IFSOCK:
                        typestr = pkgcore_SOCKSTR;
                        break;
                    case S_IFIFO:
                        typestr = pkgcore_FIFOSTR;
                        break;
                    default:
                        /* XXX does this make sense? probably not. */
                        typestr = pkgcore_UNKNOWNSTR;
                }
            }
            break;

            default:
                /* XXX does this make sense? probably not. */
                typestr = pkgcore_UNKNOWNSTR;
        }

        PyObject *namestr = PyString_FromString(name);
        if (!namestr) {
            Py_DECREF(result);
            result = NULL;
            break;
        }
        /* Slight hack: incref typestr after our error checks. */
        PyObject *tuple = PyTuple_Pack(2, namestr, typestr);
        Py_DECREF(namestr);
        if (!tuple) {
            Py_DECREF(result);
            result = NULL;
            break;
        }
        Py_INCREF(typestr);

        int res = PyList_Append(result, tuple);
        Py_DECREF(tuple);
        if (res == -1) {
            Py_DECREF(result);
            result = NULL;
            break;
        }
    }
    if (closedir(the_dir) == -1) {
        return PyErr_SetFromErrno(PyExc_OSError);
    }
    return result;
}

/* Module initialization */

static PyMethodDef pkgcore_readdir_methods[] = {
    {"listdir", (PyCFunction)pkgcore_readdir_listdir, METH_VARARGS,
     "listdir(path, followSymlinks=True, kinds=everything)"},
    {"listdir_dirs", (PyCFunction)pkgcore_readdir_listdir_dirs, METH_VARARGS,
     "listdir_dirs(path, followSymlinks=True)"},
    {"listdir_files", (PyCFunction)pkgcore_readdir_listdir_files, METH_VARARGS,
     "listdir_files(path, followSymlinks=True)"},
    {"readdir", (PyCFunction)pkgcore_readdir_read_dir, METH_VARARGS,
     "read_dir(path)"},
    {NULL}
};

PyDoc_STRVAR(
    pkgcore_module_documentation,
    "C reimplementation of some of pkgcore.util.osutils");

PyMODINIT_FUNC
init_readdir()
{
    PyObject *m;

    /* XXX we have to initialize these before we call InitModule3 because
     * the pkgcore_readdir_methods use them, which screws up error handling.
     */
    pkgcore_DIRSTR = PyString_FromString("directory");
    pkgcore_CHRSTR = PyString_FromString("chardev");
    pkgcore_BLKSTR = PyString_FromString("block");
    pkgcore_REGSTR = PyString_FromString("file");
    pkgcore_FIFOSTR = PyString_FromString("fifo");
    pkgcore_LNKSTR = PyString_FromString("symlink");
    pkgcore_SOCKSTR = PyString_FromString("socket");
    pkgcore_UNKNOWNSTR = PyString_FromString("unknown");

    if (!(pkgcore_DIRSTR &&
          pkgcore_CHRSTR &&
          pkgcore_BLKSTR &&
          pkgcore_REGSTR &&
          pkgcore_FIFOSTR &&
          pkgcore_LNKSTR &&
          pkgcore_SOCKSTR &&
          pkgcore_UNKNOWNSTR)) {
        Py_FatalError("Can't initialize module _readdir (strings)");
    }

    /* Create the module and add the functions */
    m = Py_InitModule3("_readdir", pkgcore_readdir_methods,
                       pkgcore_module_documentation);
    if (!m)
        return;

    /* Success! */
}
