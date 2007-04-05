/*
 * Copyright: 2004-2007 Brian Harring
 * Copyright: 2005 Mike Frysinger
 * Copyright: 2006 Marien Zwart
 * License: GPL2
 */

#define PY_SSIZE_T_CLEAN

#include <Python.h>
#include <snakeoil/py24-compatibility.h>

PyDoc_STRVAR(
    module_doc,
    "Filter a bash env dump.\n"
    );

#include <regex.h>
#include "bmh_search.h"

#define SPACE_PARSING            2
#define COMMAND_PARSING          1

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


static const inline char *
is_function(const char *p, char **start, char **end)
{
    #define SKIP_SPACES(p) while('\0' != *(p) && \
        (' ' == *(p) || '\t' == *(p))) ++p;
    #define FUNC_LEN 8
    SKIP_SPACES(p);
    if(strncmp(p, "function", FUNC_LEN) == 0)
        p += FUNC_LEN;
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

// zero for doesn't match, !0 for matches.
static int
regex_matches(regex_t *re, const char *buff, int desired_value)
{
    INFO("match %s, desired %d", buff, desired_value);
    regmatch_t match[1];
    match[0].rm_so = match[0].rm_eo = -1;
    assert(buff != NULL);
    assert(re != NULL);
    regexec(re, buff, 1, match, 0);
/*    fprintf(stderr,"result was %i for %s, returning %i\n", match[0].rm_so,
        buff,i);
*/
    INFO("got %d", match[0].rm_so);
    return match[0].rm_so != desired_value ? 1 : 0;
}

static const char *
process_scope(PyObject *out, const char *start, const char *buff,
              const char *end,
              regex_t *var_re, regex_t *func_re, int desired_var_match,
              int desired_func_match, const char endchar)
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
            asprintf(&temp_string, "%.*s", (int)(e - s), s);
            INFO("matched func name '%s'", temp_string);
            /* output it if it doesn't match */

            new_p = process_scope(
                NULL, start, new_p, end, NULL, NULL, 0, 0, '}');
            INFO("ended processing  '%s'", temp_string);
            if (func_re != NULL && regex_matches(func_re, temp_string,
                desired_func_match)) {

                /* well, it matched.  so it gets skipped. */
                INFO("filtering func '%s'", temp_string);
                window_end = com_start;
            }

            p = new_p;
            free(temp_string);
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
            asprintf(&temp_string, "%.*s", (int)(e - s), s);
            INFO("matched env assign '%s'", temp_string);

            if (var_re && regex_matches(var_re, temp_string,
                desired_var_match)) {
                //this would be filtered.
                INFO("filtering var '%s'", temp_string);
                window_end = com_start;
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
    memcpy(temp_string, p, here_len);
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
        return process_scope(NULL, start, p + 1, end, NULL, NULL, 0, 0, ')') + 1;
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

/* Set a sensible exception for a failed regex compilation. */
static void
regex_exc(regex_t* reg, int result)
{
    ssize_t len = regerror(result, reg, NULL, 0);
    char *buffer = malloc(len);
    if (!buffer) {
        PyErr_NoMemory();
        return;
    }
    regerror(result, reg, buffer, len);
    PyErr_SetString(PyExc_ValueError, buffer);
    free(buffer);
}


PyDoc_STRVAR(
    run_docstring,
    "Print a filtered environment.\n"
    "\n"
    "@param out: file-like object to write to.\n"
    "@param file_buff: string containing the environment to filter.\n"
    "    Should end in '\0'.\n"
    "@param vsr: result of build_regex_string or C{None}, for variables.\n"
    "@param vsr: result of build_regex_string or C{None}, for functions.\n"
    "@param desired_var_match: boolean indicating vsr should match or not.\n"
    "@param desired_func_match: boolean indicating fsr should match or not.\n"
    );

static PyObject *
pkgcore_filter_env_run(PyObject *self, PyObject *args, PyObject *kwargs)
{
    /* Arguments. */
    PyObject *out, *desired_var_match_obj, *desired_func_match_obj;
    const char *file_buff, *vsr, *fsr;
    Py_ssize_t file_size;

    /* Other vars. */

    regex_t vre, *pvre, fre, *pfre;
    int result, desired_func_match, desired_var_match;

    static char *kwlist[] = {"out", "file_buff", "vsr", "fsr",
                             "desired_var_match", "desired_func_match", NULL};
    if (!PyArg_ParseTupleAndKeywords(args, kwargs, "Os#zzOO", kwlist,
                                     &out, &file_buff, &file_size, &vsr, &fsr,
                                     &desired_var_match_obj,
                                     &desired_func_match_obj))
        return NULL;

    desired_func_match = PyObject_IsTrue(desired_func_match_obj);
    if (desired_func_match < 0)
        return NULL;
    if (desired_func_match)
        desired_func_match = -1;

    desired_var_match = PyObject_IsTrue(desired_var_match_obj);
    if (desired_var_match < 0)
        return NULL;
    if (desired_var_match)
        desired_var_match = -1;

    if (file_buff[file_size] != '\0') {
        PyErr_SetString(PyExc_ValueError, "file_buff should end in NULL");
        return NULL;
    }

    if (fsr) {
        result = regcomp(&fre, fsr, REG_EXTENDED);
        if (result) {
            regex_exc(&fre, result);
            regfree(&fre);
            return NULL;
        }
        pfre = &fre;
    } else
        pfre = NULL;

    if (vsr) {
        result = regcomp(&vre, vsr, REG_EXTENDED);
        if (result) {
            if (pfre)
                regfree(pfre);
            regex_exc(&vre, result);
            regfree(&vre);
            return NULL;
        }
        pvre = &vre;
    } else
        pvre = NULL;

    const char *res_p = process_scope(
        out, file_buff, file_buff, file_buff + file_size, pvre, pfre,
        desired_var_match, desired_func_match, '\0');

    if (pvre)
        regfree(pvre);
    if (pfre)
        regfree(pfre);

    if (!res_p) {
        PyErr_SetString(PyExc_ValueError, "Parsing failed");
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
init_filter_env()
{
    /* External objects. */
    PyObject *s = PyString_FromString("pkgcore.log");
    if (!s)
        return;
    PyObject *log = PyImport_Import(s);
    Py_DECREF(s);
    if (!log)
        return;
    PyObject *logger = PyObject_GetAttrString(log, "logger");
    Py_DECREF(log);
    if (!logger)
        return;
    log_debug = PyObject_GetAttrString(logger, "debug");
    if (!log_debug) {
        Py_DECREF(logger);
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
