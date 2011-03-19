/*
 * Copyright: 2004-2011 Brian Harring
 * Copyright: 2005 Mike Frysinger
 * Copyright: 2006 Marien Zwart
 * License: BSD 3 clause
 */

#define PY_SSIZE_T_CLEAN

#include <Python.h>
#include <snakeoil/common.h>

PyDoc_STRVAR(
	module_doc,
	"Filter a bash env dump.\n"
	);

#include <regex.h>
#include "bmh_search.h"

#define SPACE_PARSING			2
#define COMMAND_PARSING		  1

static inline const char *walk_command_escaped_parsing(
	const char *start, const char *p, const char *end, const char endchar);
static inline const char *walk_statement_pound(
	const char *start, const char *p, char endchar);
static const char *walk_command_complex(const char *start, const char *p,
										const char *end,
	char endchar, const char interpret_level);
static inline const char *walk_statement_no_parsing(const char *p,
	const char *end, const char endchar);
static inline const char *walk_statement_dollared_quote_parsing(const char *p,
	const char *end, const char endchar);
static const char *walk_dollar_expansion(const char *start, const char *p,
										 const char *end,
										 char endchar, char disable_quote);


#ifndef Py_MEMCPY
#define Py_MEMCPY memcpy
#endif

static PyObject *log_info = NULL;
static PyObject *log_debug = NULL;
static PyObject *write_str = NULL;

/* Log a message. Returns -1 on error, 0 on success. */
static int
debug_print(PyObject *logfunc, const char *format, ...)
{
	/* Sanity check. Should not happen. */
	if (!logfunc)
		return -1;
	va_list vargs;
	va_start(vargs, format);
	PyObject *message = PyString_FromFormatV(format, vargs);
	va_end(vargs);
	if (!message)
		return -1;
	PyObject *result = PyObject_CallFunctionObjArgs(logfunc, message, NULL);
	Py_DECREF(message);
	return result ? 0 : -1;
}

#define INFO(fmt, args...) debug_print(log_info, fmt, ## args)
#define DEBUG(fmt, args...) debug_print(log_info, fmt, ## args)

static void
do_envvar_callback(PyObject *callback, const char *str)
{
	if(!callback)
		return;
	PyObject *pstr = PyString_FromString(str);
	if(!pstr)
		return;
	PyObject *result = PyObject_CallFunctionObjArgs(callback, pstr, NULL);
	Py_DECREF(pstr);
	if(result) {
		Py_DECREF(result);
	}
}


static const inline char *
is_function(const char *p, char **start, char **end)
{
	#define SKIP_SPACES(p) while('\0' != *(p) && \
		(' ' == *(p) || '\t' == *(p))) ++p;
	#define FUNC_LEN 8
	SKIP_SPACES(p);
	if(strncmp(p, "function", FUNC_LEN) == 0) {
		if(isspace(p[FUNC_LEN])) {
			p += FUNC_LEN;
		}
	}
	while('\0' != *p && isspace(*p))
		++p;
	*start = (char *)p;
	while('\0' != *p && ' ' != *p && '\t' != *p && '\n' != *p &&
		'=' != *p && '"' != *p && '\'' != *p && '(' != *p && ')' != *p)
		++p;
	*end = (char *)p;
	if(*end == *start)
		return NULL;
	SKIP_SPACES(p);
	if('\0' == *p || '(' != *p)
		return NULL;
	++p;
	SKIP_SPACES(p);
	if('\0' == *p || ')' != *p)
		return NULL;
	++p;
	while('\0' != *p && isspace(*p))
		++p;
	if('\0' == *p || '{' != *p)
		return NULL;
	return ++p;
}


static inline const char *
is_envvar(const char *p, char **start, char **end)
{
	SKIP_SPACES(p);
	*start = (char *)p;
	for(;;) {
		switch(*p) {
		case '\0':
		case '"':
		case '\'':
		case '(':
		case ')':
		case '-':
		case ' ':
		case '\t':
		case'\n':
			return NULL;
		case '=':
			if(p == *start)
				return NULL;
			*end = (char *)p;
			return ++p;
		default:
			++p;
		}
	}
}

// zero for doesn't match, 1 for matches, -1 for error.
static int
regex_matches(PyObject *re, const char *buff)
{
	INFO("match %s", buff);
	assert(buff != NULL);
	assert(re != NULL);
	PyObject *str = PyString_FromString(buff);
	if (!str)
		return -1;

	PyObject *match_ret = PyObject_CallFunctionObjArgs(re, str, NULL);
	Py_DECREF(str);
	if(!match_ret)
		return -1;

	int result = PyObject_IsTrue(match_ret);
	Py_DECREF(match_ret);
	return result;
}

static const char *
process_scope(PyObject *out, const char *start, const char *buff,
			  const char *end,
			  PyObject *var_matcher, PyObject *func_matcher,
			  const char endchar, PyObject *envvar_callback)
{
	const char *p = NULL;
	const char *window_start = NULL, *window_end = NULL;
	const char *new_p = NULL;
	const char *com_start = NULL;
	char *s = NULL;
	char *e = NULL;
	char *temp_string = NULL;

	regmatch_t matches[3];
	p = buff;
	matches[0].rm_so = matches[1].rm_so = matches[2].rm_so = -1;

	window_start = buff;
	window_end = NULL;
	while (p < end && *p != endchar) {

		/* wander forward to the next non space */
		if (window_end != NULL) {
			if (out) {
				PyObject *string = PyString_FromStringAndSize(
					window_start, window_end - window_start);
				if (!string)
					return NULL;
				PyObject *result = PyObject_CallMethodObjArgs(
					out, write_str, string, NULL);
				Py_DECREF(string);
				if (!result)
					return NULL;
				Py_DECREF(result);
			}
			window_start = p;
			window_end = NULL;
		}
		com_start = p;
		if (isspace(*p)) {
			++p;
			continue;
		}

		/* ignore comments */
		if (*p == '#') {
			p = walk_statement_pound(start, p, endchar);
			continue;
		}

		if(NULL != (new_p = is_function(p, &s, &e))) {
			if(-1 == asprintf(&temp_string, "%.*s", (int)(e - s), s))
				return NULL;
			INFO("matched func name '%s'", temp_string);
			/* output it if it doesn't match */

			new_p = process_scope(
				NULL, start, new_p, end, NULL, NULL, '}', NULL);
			INFO("ended processing  '%s'", temp_string);
			if (func_matcher) {
				int regex_result = regex_matches(func_matcher, temp_string);
				if (-1 == regex_result) {
					free(temp_string);
					return NULL;
				}
				if (regex_result) {
					/* well, it matched.  so it gets skipped. */
					INFO("filtering func '%s'", temp_string);
					window_end = com_start;
				}
			}

			free(temp_string);
			if(!new_p)
				return NULL;
			p = new_p;
			++p;
			continue;
		}
		// check for env assignment
		if (NULL == (new_p = is_envvar(p, &s, &e))) {
			//exactly as it sounds, non env assignment.
			p = walk_command_complex(start, p, end,
				endchar, COMMAND_PARSING);
			if (!p)
				return NULL;
			// icky icky icky icky
			if (p < end && *p != endchar)
				++p;
		} else {
			//env assignment
			if(-1 == asprintf(&temp_string, "%.*s", (int)(e - s), s))
				return NULL;
			INFO("matched env assign '%s'", temp_string);

			do_envvar_callback(envvar_callback, temp_string);

			if (var_matcher) {
				int regex_result = regex_matches(var_matcher, temp_string);
				if (-1 == regex_result) {
					free(temp_string);
					return NULL;
				}
				if (regex_result) {
					//this would be filtered.
					INFO("filtering var '%s'", temp_string);
					window_end = com_start;
				}
			}

			free(temp_string);

			p = new_p;
			if (p >= end) {
				return p;
			}

			while(p < end && !isspace(*p) && ';' != *p) {
				if ('\'' == *p)
					p = walk_statement_no_parsing(p + 1, end, '\'') + 1;
				else if ('"' == *p || '`' == *p)
					p = walk_command_escaped_parsing(start, p + 1, end,
						*p) + 1;
				else if ('(' == *p) {
					p = walk_command_escaped_parsing(start, p + 1, end,
						')') + 1;
				} else if ('$' == *p) {
					++p;
					if (p >= end) {
						continue;
					}
					p = walk_dollar_expansion(start, p, end, endchar,
						endchar);
					continue;
				} else {
					// blah=cah ; single word.
					p = walk_command_complex(start, p, end, ' ',
						SPACE_PARSING);
					if (!p) {
						return NULL;
					}
				}
			}
		}
	}

	if (out) {
		if (window_end == NULL)
			window_end = p;
		if (window_end > end)
			window_end = end;
		PyObject *string = PyString_FromStringAndSize(
			window_start, window_end - window_start);
		if (!string)
			return NULL;
		PyObject *result = PyObject_CallMethodObjArgs(
			out, write_str, string, NULL);
		Py_DECREF(string);
		if (!result)
			return NULL;
		Py_DECREF(result);
	}

	return p;
}


static inline const char *
walk_statement_no_parsing(const char *p, const char *end, const char endchar)
{
	while (p < end && endchar != *p) {
		++p;
	}
	return p;
}

static inline const char *
walk_statement_dollared_quote_parsing(const char *p, const char *end,
	const char endchar)
{
	while (p < end) {
		if (*p == endchar) {
			return p;
		} else if ('\\' == *p) {
			++p;
		}
		++p;
	}
	return p;
}

/* Sets an exception and returns NULL if out of memory. */
static const char *
walk_here_statement(const char *start, const char *p, const char *end)
{
	char *end_here, *temp_string;
	++p;
	/* DEBUG("starting here processing for COMMAND for level 2 at p == '%.10s'",
	 * p); */
	if (p >= end) {
		fprintf(stderr, "bailing\n");
		return p;
	}
	if ('<' == *p) {
		/* d2printf("correction, it's a third level here.  Handing back to "
		 * "command parsing\n"); */
		return ++p;
	}
	while (p < end && (isspace(*p) || '-' == *p))
		++p;

	if ('\'' == *p || '"' == *p) {
		end_here = (char *)walk_statement_no_parsing(p + 1, end, *p);
		++p;
	} else {
		end_here = (char *)walk_command_complex(start, p, end,
												' ', SPACE_PARSING);
		if (!end_here)
			return NULL;
	}

	/* INFO("end_here=%.5s",end_here); */
	temp_string = malloc(end_here -p + 1);
	if (!temp_string) {
		PyErr_NoMemory();
		return NULL;
	}
	int here_len = end_here - p;
	Py_MEMCPY(temp_string, p, here_len);
	temp_string[here_len] = '\0';
	/* d2printf("matched len('%zi')/'%s' for a here word\n", end_here - p,
	 * temp_string); */
	/* XXX watch this.  potential for horkage.  need to do the quote
		removal thing.
		this sucks.
	*/
	++end_here;
	if (end_here >= end) {
		free(temp_string);
		return end_here;
	}

	end_here = (char *)bmh_search((unsigned char*)temp_string,
								  (unsigned char*)end_here, end - end_here);
	while(end_here) {
		char *i = end_here + here_len;
		if (';' == *i || '\n' == *i || '\r' == *i) {
			i = end_here - 1;
			while (i != p && ('\t' == *i || ' ' == *i))
				--i;
			if (i != p && '\n' == *i)
				break;
		}
		end_here = (char *)bmh_search((unsigned char*)temp_string,
									  (unsigned char*)(end_here + here_len),
									  end - end_here - here_len);
	}
	INFO("bmh returned %p", end_here);
	free(temp_string);

	if (!end_here) {
		return end;
	}
	/* d2printf("bmh = %.10s\n", end_here); */
	return end_here + here_len;
}

static const char *
walk_statement_pound(const char *start, const char *p, char endchar)
{
	if (p > start && !isspace(p[-1]))
		return p + 1;
	if ('`' == endchar) {
		while('\0' != *p && '\n' != *p && endchar != *p)
			p++;
		return p;
	}
	while('\0' != *p && '\n' != *p) {
		++p;
	}
	return p;
}

/* Sets an exception and returns NULL if out of memory. */
static const char *
walk_command_complex(const char *start, const char *p, const char *end,
					 char endchar, const char interpret_level)
{
	while (p < end) {
		if (*p == endchar) {
			if('}' != endchar || start == p)
				return p;
			if('\n' == p[-1] || ';' == p[-1]) {
				return p;
			}
		} else if ((interpret_level == COMMAND_PARSING && (';'==*p || '\n'==*p)) ||
			(interpret_level == SPACE_PARSING && isspace(*p))) {
			return p;
		} else if ('\\' == *p) {
			++p;
		} else if ('<' == *p) {
			if(p < end - 1 && '<' == p[1] && interpret_level == COMMAND_PARSING) {
				p = walk_here_statement(start, p + 1, end);
				if (!p)
					return NULL;
				/* We continue immediately; walk_here deposits us at
				 * the end of the here op, not consuming the final
				 * delimiting char since it may be an endchar
				 */
				continue;
			} else {
				DEBUG("noticed '<', interpret_level=%i\n", interpret_level);
			}
		} else if ('#' == *p) {
			/* echo x#y == x#y, echo x;#a == x */
			if (start == p || isspace(p[-1]) || ';' == p[-1]) {
				p = walk_statement_pound(start, p, 0);
				continue;
			}
		} else if ('$' == *p) {
			p = walk_dollar_expansion(start, p + 1, end, endchar, 0);
			continue;
		} else if ('{' == *p) {
			p = walk_command_escaped_parsing(start, p + 1, end, '}');
		} else if ('(' == *p && interpret_level == COMMAND_PARSING) {
			p = walk_command_escaped_parsing(start, p + 1, end, ')');
		} else if ('`' == *p || '"' == *p) {
			p = walk_command_escaped_parsing(start, p + 1, end, *p);
		} else if ('\'' == *p && '"' != endchar) {
			p = walk_statement_no_parsing(p + 1, end, '\'');
		}
		++p;
	}
	return p;
}

static const char *
walk_command_escaped_parsing(const char *start, const char *p,
							 const char *end, const char endchar)
{
	while (p < end) {
		if (*p == endchar) {
			return p;
		} else if ('\\' == *p) {
			++p;
		} else if ('{' == *p) {
			if('"' != endchar) {
				p = walk_command_escaped_parsing(start, p + 1, end, '}');
			}
		} else if ('(' == *p) {
			if('"' != endchar) {
				p = walk_command_escaped_parsing(start, p + 1, end, ')');
			}
		} else if ('`' == *p || '"' == *p) {
			p = walk_command_escaped_parsing(start, p + 1, end, *p);
		} else if ('\'' == *p && '"' != endchar) {
			p = walk_statement_no_parsing(p + 1, end, '\'');
		} else if('$' == *p) {
			p = walk_dollar_expansion(start, p + 1, end, endchar, endchar == '"');
			continue;
		} else if ('#' == *p && endchar != '"') {
			p = walk_statement_pound(start, p, endchar);
			continue;
		}
		++p;
	}
	return p;
}

static const char *
walk_dollar_expansion(const char *start, const char *p, const char *end,
					  char endchar, char disable_quote)
{
	if ('(' == *p)
		return process_scope(NULL, start, p + 1, end, NULL, NULL, ')', NULL) + 1;
	if ('\'' == *p && !disable_quote)
		return walk_statement_dollared_quote_parsing(p + 1, end, '\'') + 1;
	if ('{' != *p) {
		if ('$' == *p)
			// short circuit it.
			return p + 1;
		while (p < end && endchar != *p) {
			if (isspace(*p))
				return p;
			if ('$' == *p)
				return walk_dollar_expansion(start, p + 1, end, endchar, 0);
			if (!isalnum(*p)) {
				if ('_' != *p) {
					return p;
				}
			}
			++p;
		}

		return p >= end ? end : p;
	}
	++p;
	// shortcut ${$} to avoid going too deep. ${$a} isn't valid so no concern
	if ('$' == *p)
		return p + 1;
	while (p < end && '}' != *p) {
		if ('$' == *p)
			p = walk_dollar_expansion(start, p + 1, end, endchar, 0);
		else
			++p;
	}
	return p + 1;
}


PyDoc_STRVAR(
	run_docstring,
	"Print a filtered environment.\n"
	"\n"
	"@param out: file-like object to write to.\n"
	"@param file_buff: string containing the environment to filter.\n"
	"	Should end in '\0'.\n"
	"@param vsr: result of build_regex_string or C{None}, for variables.\n"
	"@param vsr: result of build_regex_string or C{None}, for functions.\n"
	"@param desired_var_match: boolean indicating vsr should match or not.\n"
	"@param desired_func_match: boolean indicating fsr should match or not.\n"
	);

static PyObject *
pkgcore_filter_env_run(PyObject *self, PyObject *args, PyObject *kwargs)
{
	/* Arguments. */
	PyObject *out, *envvar_callback=NULL;
	const char *file_buff;
	PyObject *var_matcher, *func_matcher;
	Py_ssize_t file_size;

	char *res_p = NULL;

	static char *kwlist[] = {"out", "file_buff", "vsr", "fsr",
							 "global_envvar_callback", NULL};

	if (!PyArg_ParseTupleAndKeywords(args, kwargs, "Os#OO|O", kwlist,
									 &out, &file_buff, &file_size,
									 &var_matcher, &func_matcher,
									 &envvar_callback))
		return NULL;

	int result = PyObject_IsTrue(func_matcher);
	if (result < 0)
		return NULL;
	if (!result)
		func_matcher = NULL;

	result = PyObject_IsTrue(var_matcher);
	if (result < 0)
		return NULL;
	if (!result)
		var_matcher = NULL;

	if (file_buff[file_size] != '\0') {
		PyErr_SetString(PyExc_ValueError, "file_buff should end in NULL");
		return NULL;
	}

	if(envvar_callback) {
		int true_ret = PyObject_IsTrue(envvar_callback);
		if(-1 == true_ret) {
			goto filter_env_cleanup;
		}
		if(!true_ret) {
			envvar_callback = (PyObject *)NULL;
		}
	}

	res_p = (char *)process_scope(
		out, file_buff, file_buff, file_buff + file_size, var_matcher, func_matcher,
		'\0', envvar_callback);

filter_env_cleanup:

	if (!res_p) {
		if (!PyErr_Occurred()) {
			PyErr_SetString(PyExc_ValueError, "Parsing failed");
		}
		return NULL;
	}
	Py_RETURN_NONE;
}

static PyMethodDef pkgcore_filter_env_methods[] = {
	{"run", (PyCFunction)pkgcore_filter_env_run, METH_VARARGS | METH_KEYWORDS,
	 run_docstring},
	{NULL}
};

PyMODINIT_FUNC
init_filter_env(void)
{
	/* External objects. */

	PyObject *logger = NULL;
	snakeoil_LOAD_SINGLE_ATTR(logger, "pkgcore.log", "logger");

	Py_CLEAR(log_debug);
	Py_CLEAR(log_info);
	Py_CLEAR(write_str);

	log_debug = PyObject_GetAttrString(logger, "debug");
	if (!log_debug) {
		Py_CLEAR(logger);
		return;
	}
	log_info = PyObject_GetAttrString(logger, "info");
	Py_DECREF(logger);
	if (!log_info) {
		Py_CLEAR(log_debug);
		return;
	}

	/* String constants. */
	write_str = PyString_FromString("write");
	if (!write_str) {
		Py_CLEAR(log_info);
		Py_CLEAR(log_debug);
		return;
	}

	/* XXX the returns above this point trigger SystemErrors. */
	Py_InitModule3("_filter_env", pkgcore_filter_env_methods, module_doc);
}
