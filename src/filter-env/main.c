/* 
 Copyright: 2004-2006 Brian Harring
 Copyright: 2005 Mike Vapier
 License: GPL2
 $Id:$
*/

#define _GNU_SOURCE
#include <sys/types.h>
#include <sys/stat.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <fcntl.h>
#include <getopt.h>
#include <regex.h>
#include <unistd.h>
#include <ctype.h>
#include <assert.h>
#include "bmh_search.h"

#ifdef __GNUC__
# define no_return __attribute__ ((noreturn))
#else
# define no_return
#endif

#define USAGE_FAIL   1
#define MEM_FAIL     2
#define IO_FAIL      3
#define PARSE_FAIL   4

#define SPACE_PARSING            4
#define ESCAPED_PARSING          3
#define COMMAND_PARSING          2
#define DOLLARED_QUOTE_PARSING   1
#define NO_PARSING               0

#define DESIRED_MATCH 		-1
#define DESIRED_NONMATCH	0

static int regex_matches(regex_t *re, const char *buff, int desired_value);
static const char *process_scope(FILE *out_fd, const char *buff, const char *end, regex_t *var_re, regex_t *func_re, char endchar);
static int append_to_filter_list(char ***list, int *count, int *alloced, const char *string);
static const char *build_regex_string(const char **list, size_t count);
static inline const char *walk_command_no_parsing(const char *p, const char *end, const char endchar);
static inline const char *walk_command_dollared_parsing(const char *p, const char *end, const char endchar);
static inline const char *walk_command_escaped_parsing(const char *p, const char *end, const char endchar);
static inline const char *walk_command_pound(const char *p);
static const char *walk_command_complex(const char *p, const char *end, char endchar, const char interpret_level);
static inline const char *is_function(const char *p, char **start, char **end);
static inline const char *is_envvar(const char *p, char **start, char **end);
static void *xmalloc(size_t size);
no_return void usage(int exit_status);

/* hackity hack hack hackity hack. */
static int desired_func_match = DESIRED_MATCH;
static int desired_var_match = DESIRED_MATCH;


static int debugging;
#define d1printf(fmt, args...) dprintf(1, fmt , ## args)
#define d2printf(fmt, args...) dprintf(2, fmt , ## args)
#define dprintf(level, fmt, args...) \
	do { \
		if (debugging >= level) \
			fprintf(stderr, "%s:%i: " fmt, __FUNCTION__, __LINE__ , ## args); \
	} while (0)

#define err(exit_code, expr...) \
	do { \
		fprintf(stderr, expr); \
		exit(exit_code); \
	} while (0)


static void *xmalloc(size_t size) {
	void *ret = malloc(size);
	if (ret == NULL && size)
		err(MEM_FAIL, "could not malloc %zi bytes\n", size);
	return ret;
}


no_return void usage(int exit_status)
{
	fprintf((exit_status ? stderr : stdout),
		"Usage: [-i file] [-F] [-f func1,func2,func3,...] [-V] [-v var1,var2,var3,...]\n");
	exit(exit_status);
}

int main(int argc, char *const *argv)
{
	FILE *file_in = NULL;
	FILE *file_out = NULL;
	char **funcs = NULL, **vars = NULL;
	char *file_buff = NULL;
	const char *end = NULL;
	int funcs_count = 0,   vars_count = 0;
	int funcs_alloced = 0, vars_alloced = 0;
	int c;
	size_t  file_size=0, buff_alloced = 0;
	regex_t vre, *pvre = NULL;
	regex_t fre, *pfre = NULL;
	const char *fsr, *vsr;
	char *temp = NULL;
	struct stat st;
	debugging = 0;

	funcs = (char **)xmalloc(sizeof(char *) * 10);
	vars = (char **)xmalloc(sizeof(char *) * 10);

	while ((c = getopt(argc, argv, "VFhi:f:v:d")) != EOF) {
		d2printf("c = %i\n", c);

		switch(c) {
		case 'd':
			debugging++;
			break;
		case 'i':
			if (file_in != NULL)
				err(USAGE_FAIL, "-i cannot be specified twice. bailing\n");
			if (stat(optarg, &st))
				err(IO_FAIL, "error stating file %s, bailing\n", optarg);
			file_size = st.st_size;
			file_in = fopen(optarg, "r");
			if (file_in == NULL)
				err(IO_FAIL, "error opening file %s, bailing\n", optarg);
			break;
		case 'f':
			d2printf("wassube.  opt_art=%s\n", optarg);
			if (append_to_filter_list(&funcs, &funcs_count, &funcs_alloced, optarg))
				err(USAGE_FAIL, "-f arg '%s', isn't valid.  must be comma delimited\n", optarg);
			break;
		case 'v':
			if (append_to_filter_list(&vars, &vars_count, &vars_alloced, optarg))
				err(USAGE_FAIL, "-v arg '%s', isn't valid.  must be comma delimited\n", optarg);
			break;
		case 'F':
			desired_func_match = DESIRED_NONMATCH;
			break;
		case 'V':
			desired_var_match = DESIRED_NONMATCH;
			break;
		case 'h':
			printf("filter-env: compiled %s\n", __DATE__);
			usage(EXIT_SUCCESS);
		default:
			usage(USAGE_FAIL);
		}
	}
	if (optind != argc)
		usage(USAGE_FAIL);

	if (file_size == 0) {
		/* print usage if user attempts to call filter-env from cmdline directly */         
		if (ttyname(0) != NULL)
			usage(EXIT_FAILURE);
		file_in = stdin;
	} else
		fclose(stdin);
	file_out = stdout;

	fsr = build_regex_string((const char **)funcs, funcs_count);
	d1printf("fsr buffer = %s\n", fsr);
	vsr = build_regex_string((const char **)vars, vars_count);
	d1printf("vsr buffer = %s\n", vsr);
	if (fsr) {
		// prefix ^
		temp = (char *)xmalloc(strlen(fsr) + 3);
		temp[0] = '^'; temp[1] = '\0';
		temp = strcat(temp, fsr);
		temp = strcat(temp, "$");
		d1printf("fsr pattern is %s\n", temp);
		regcomp(&fre, temp, REG_EXTENDED);
		free(temp);
		temp = NULL;
		pfre = &fre;
		free((void*)fsr);
		fsr = NULL;
	} else
		pfre = NULL;

	if (vsr) {
		temp = (char *)xmalloc(strlen(vsr) + 3);
		temp[0] = '^'; temp[1] = '\0';
		temp = strcat(temp, vsr);
		temp = strcat(temp, "$");
		d1printf("vsr pattern is %s\n", temp);
		regcomp(&vre, temp, REG_EXTENDED);
		free(temp);
		temp = NULL;
		pvre = &vre;
		free((void*)vsr);
		vsr = NULL;
	} else
		pvre = NULL;

	if (file_size) {
		file_buff = (char *)xmalloc(file_size + 1);
		if (file_size != fread(file_buff, 1, file_size, file_in))
			err(IO_FAIL, "failed reading file\n");
	} else {
		file_buff = (char *)xmalloc(4096);
		buff_alloced = 4096;
		c = 4096;
		while (c > 0) {
			c = fread(file_buff+file_size, 1, 4096, file_in);
			file_size += c;
			/* realloc +1 for null termination. */
			if (buff_alloced < file_size + 4096) {
				if ((file_buff = (char *)realloc(file_buff, buff_alloced + 4096)) == NULL) {
					err(MEM_FAIL, "failed allocing needed memory for file.\n");
				}
				buff_alloced += 4096;
			}
		}
		d1printf("read %zi bytes\n", file_size);
	}
	file_buff[file_size] = '\0';
	fclose(file_in);

	end = process_scope(file_out,file_buff, file_buff + file_size,pvre, pfre, '\0');
	d1printf("%zi == %zi\n", end - file_buff, file_size);

	fflush(file_out);
	fclose(file_out);
	free((void*)fsr);
	free((void*)vsr);
	free(file_buff);
	exit(0);
}

static int
append_to_filter_list(char ***list, int *count, int *alloced, const char *string)
{
	char *d = NULL;
	char **l = *list;
	char *s = NULL;

	s = strdup(string);
	d = strtok(s, ",");
	if (d == NULL) {
		free(s);
		return 1;
	}

	while (d != NULL) {
		if (*alloced == *count) {
			if ((l=(char **)realloc(l, sizeof(char*) * (*alloced + 10))) == NULL)
				return 1;
			*alloced += 10;
		}
		l[*count] = d;
		(*count)++;
		d = strtok(NULL, ",");
	}
	*list = l;
	return 0;
}

const char *
build_regex_string(const char **list, size_t count)
{
	char *buff, *p;
	const char *p2;
	size_t l = 0, x = 0;
	int escaped = 0;

	for (x = 0; x < count; ++x) {
		l += strlen(list[x]) + 1;
		p2 = list[x];
		// if it's ., substitute a [^ =] internally.
		while (*p2 != '\0') {
			if (*p2 == '.')
				l += 4;
			++p2;
		}
	}
	if (l == 0)
		return NULL;
	//shave off the extra '|' char, add in '(...)'.  hence, 3.
	buff = xmalloc(l + 5);
	memset(buff,0,l+4);
	buff[0] = '(';
	p=buff + 1;
	for (x=0; x < count; ++x) {
		p2 = list[x];
		escaped = 0;
		while (*p2 != '\0') {
			if (*p2 == '.' && escaped == 0) {
				strcat(p,"[^= ]");
				p += 4;
			} else if (*p2 == '\\') {
				*p = *p2;
				++p2;
				++p;
				escaped ^= 1;
				continue;
			} else {
				*p = *p2;
			}
			++p;
			++p2;
			escaped=0;
		}
		*p = '|';
		++p;
	}
	p[-1] = ')';
	p[0] = '\0';
	return buff;
}


static const inline char *
is_function(const char *p, char **start, char **end)
{
	#define SKIP_SPACES(p) while('\0' != *(p) && (' ' == *(p) || '\t' == *(p))) ++p;
	#define FUNC_LEN 8
	SKIP_SPACES(p);
	if(strncmp(p, "function", FUNC_LEN) == 0)
		p += FUNC_LEN;
	while('\0' != *p && isspace(*p))
		++p;
	*start = (char *)p;
	while('\0' != *p && ' ' != *p && '\t' != *p && '\n' != *p && '=' != *p && '"' != *p && '\'' != *p && '(' != *p && ')' != *p)
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
	regmatch_t match[1];
	match[0].rm_so = match[0].rm_eo = -1;
	assert(buff != NULL);
	assert(re != NULL);
	regexec(re, buff, 1, match, 0);
//	fprintf(stderr,"result was %i for %s, returning %i\n", match[0].rm_so, buff,i);
	return match[0].rm_so != desired_value ? 1 : 0;
}

static const char *
process_scope(FILE *out_fd, const char *buff, const char *end, regex_t *var_re, regex_t *func_re, char endchar)
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
			if (out_fd != NULL)
				fwrite(window_start, window_end - window_start, 1, out_fd);
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
			p = walk_command_pound(p);
			continue;
		}

		if(NULL != (new_p = is_function(p, &s, &e))) {
			asprintf(&temp_string, "%.*s", (int)(e - s), s);
			d1printf("matched func name '%s'\n", temp_string);
			/* output it if it doesn't match */

			new_p = process_scope(NULL, new_p, end, NULL, NULL, '}');
			d1printf("ended processing  '%s'\n", temp_string);
			if (func_re != NULL && regex_matches(func_re, temp_string, desired_func_match)) {
				/* well, it matched.  so it gets skipped. */
				d1printf("filtering func '%s'\n", temp_string);
				window_end = com_start;
			}

			p = new_p;
			free(temp_string);

			++p;
		} else {
			// check for env assignment
			if (NULL == (new_p = is_envvar(p, &s, &e))) {
				//exactly as it sounds, non env assignment.
				p = walk_command_complex(p, end, endchar, COMMAND_PARSING);
				++p;
			} else {
				//env assignment
				asprintf(&temp_string, "%.*s", (int)(e - s), s);
				p = new_p;
				d1printf("matched env assign '%s'\n", temp_string);

				if (p >= end)
					return p;

				while(p < end && !isspace(*p) && ';' != *p) {
					if ('\'' == *p)
						p = walk_command_no_parsing(p + 1, end, *p);
					else if ('"' == *p || '`' == *p)
						p = walk_command_escaped_parsing(p + 1, end, *p);
					else if ('(' == *p)
						p = walk_command_escaped_parsing(p + 1, end, ')');
					else if (isspace(*p)) {
						while (p < end && isspace(*p) && *p != '\n')
						++p;
					} else if ('$' == *p) {
						if (p + 1 >= end) {
							++p;
							continue;
						}
						if ('(' == p[1]) {
							p = walk_command_escaped_parsing(p + 2, end, ')');
						} else if ('\'' == p[1]) {
							p = walk_command_dollared_parsing(p + 2, end, '\'');
						} else if ('{' == p[1]) {
							p = walk_command_escaped_parsing(p + 2, end, '}');
						} else {
							while (p < end && !isspace(*p)) {
								if ('\\' == *p)
									++p;
								++p;
							}
						}
					} else {
						// blah=cah ; single word.
						p = walk_command_complex(p + 1, end, ' ', SPACE_PARSING);
					}
					if(isspace(*p)) {
						++p;
						break;
					}
					++p;
				}
				if (var_re && regex_matches(var_re, temp_string, desired_var_match)) {
					//this would be filtered.
					window_end = com_start;
				}
				free(temp_string);
			}
		}
	}

	if (out_fd != NULL) {
		if (window_end == NULL)
			window_end = p;
		if (window_end > end)
			window_end = end;
		fwrite(window_start, window_end - window_start, 1,out_fd);
	}

	return p;
}


static inline const char *
walk_command_no_parsing(const char *p, const char *end, const char endchar)
{
	while (p < end) {
		if (*p == endchar)
			return p;
		++p;
	}
	return p;
}

static inline const char *
walk_command_dollared_parsing(const char *p, const char *end, const char endchar)
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

static const char *
walk_here_command(const char *p, const char *end)
{
	char *end_here, *temp_string;
	++p;
	d2printf("starting here processing for COMMAND and l2 at p == '%.10s'\n", p);
	if (p >= end) {
		fprintf(stderr, "bailing\n");
		return p;
	}
	if ('<' == *p) {
		d2printf("correction, it's a third level here.  Handing back to command parsing\n");
		return ++p;
	}
	while (p < end && (isspace(*p) || '-' == *p))
		++p;
	if ('\'' == *p || '"' == *p) {
		end_here = (char *)walk_command_no_parsing(p + 1, end, *p);
		++p;
	} else {
		end_here = (char *)walk_command_complex(p, end, ' ',SPACE_PARSING);
	}
	/* d1printf("end_here=%.5s\n",end_here); */
	temp_string = xmalloc(end_here -p + 1);
	memcpy(temp_string, p, end_here - p);
	temp_string[end_here - p] = '\0';
	d2printf("matched len('%zi')/'%s' for a here word\n", end_here - p, temp_string);
	// XXX watch this.  potential for horkage.  need to do the quote removal thing.
	//this sucks.

	++end_here;
	if (end_here >= end)
		return end_here;
	end_here = (char *)bmh_search((unsigned char*)temp_string, (unsigned char*)end_here, end - end_here);
	d1printf("bmh returned %p\n", end_here);
	if (end_here) {
		d2printf("bmh = %.10s\n", end_here);
		p = end_here + strlen(temp_string) -1;
		d2printf("continuing on at %.10s\n", p);
	} else {
		p = end;
	}
	free(temp_string);
	return p;
}

static const char *
walk_command_pound(const char *p)
{
	while('\0' != *p) {
		if('\n' == *p)
			return p;
		++p;
	}
	return p;
}

static const char *
walk_command_complex(const char *p, const char *end, char endchar, const char interpret_level)
{
	int here_count = 0;
	const char *start = p;
	while (p < end) {
		if (*p == endchar || 
		    (interpret_level == COMMAND_PARSING && (';'==*p || '\n'==*p)) ||
		    (interpret_level == SPACE_PARSING && isspace(*p))) {
			return p;
		} else if ('\\' == *p) {
			++p;
		} else if ('<' == *p) {
			++here_count;
			if (2 == here_count && interpret_level == COMMAND_PARSING) {
				p = walk_here_command(p, end);
				here_count = 0;
			} else {
				d2printf("noticed '<', interpret_level=%i\n", interpret_level);
			}
		} else if ('#' == *p) {
			/* echo x#y == x#y, echo x;#a == x */
			if (start == p || isspace(p[-1]) || p[-1] == ';')
				p = walk_command_pound(p);
			else
				++p;
			continue;
		} else if ('{' == *p) {
			//process_scope.  this gets fun.
			p = walk_command_escaped_parsing(p + 1, end, '}');
		} else if ('(' == *p && interpret_level == COMMAND_PARSING) {
			p = walk_command_escaped_parsing(p + 1, end, ')');
		} else if ('`' == *p || '"' == *p) {
			p = walk_command_escaped_parsing(p + 1, end, *p);
		} else if ('\'' == *p && '"' != endchar) {
			p = walk_command_no_parsing(p + 1, end, '\'');
		}
		++p;
	}
	return p;
}

static const char *
walk_command_escaped_parsing(const char *p, const char *end, char endchar)
{
	int dollared = 0;
	while (p < end) {
		if (*p == endchar) {
			return p;
		} else if ('\\' == *p) {
			++p;
		} else if ('{' == *p) {
			//process_scope.  this gets fun.
			p = walk_command_escaped_parsing(p + 1, end, '}');
		} else if ('(' == *p) {
			// if double quote parsing, must be $(, else can be either
			if('"' != endchar || dollared) {
				p = walk_command_escaped_parsing(p + 1, end, ')');
			}
		} else if ('`' == *p || '"' == *p) {
			p = walk_command_escaped_parsing(p + 1, end, *p);
		} else if ('\'' == *p && '"' != endchar) {
			p = walk_command_no_parsing(p + 1, end, '\'');
		} else if('$' == *p) {
			// if dollared, disable, else enable
			dollared ^= 1;
		} else {
			dollared = 0;
		}
		++p;
	}
	return p;
}

