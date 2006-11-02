/*
 * Copyright: 2006 Brian Harring <ferringb@gmail.com>
 * Copyright: 2006 Marien Zwart <marienz@gentoo.org>
 * License: GPL2
 *
 * C version of some of pkgcore (for extra speed).
 */

/* This does not really do anything since we do not use the "#"
 * specifier in a PyArg_Parse or similar call, but hey, not using it
 * means we are Py_ssize_t-clean too!
 */

#ifndef PKGCORE_COMMON_INCLUDE
#define PKGCORE_COMMON_INCLUDE 1

/* Compatibility with python < 2.5 */

#if PY_VERSION_HEX < 0x02050000
typedef int Py_ssize_t;
#define PY_SSIZE_T_MAX INT_MAX
#define PY_SSIZE_T_MIN INT_MIN
typedef Py_ssize_t (*lenfunc)(PyObject *);
#endif

/* From heapy */
#include "../heapdef.h"

/* Copied from stdtypes.c in guppy */
#define INTERATTR(name) \
    if ((PyObject *)v->name == r->tgt &&                                \
        (r->visit(NYHR_INTERATTR, PyString_FromString(#name), r)))      \
		return 1;

#endif
