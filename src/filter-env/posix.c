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

#define USAGE_FAIL	1
#define MEM_FAIL	2
#define IO_FAIL		3
#define PARSE_FAIL	4

#define SPACE_PARSING		4
#define ESCAPED_PARSING		3
#define COMMAND_PARSING		2
#define DOLLARED_QUOTE_PARSING	1
#define NO_PARSING		0

void init_regexes();
void free_regexes();
int regex_matches(regex_t *re, const char *buff);
const char *process_scope(FILE *out_fd, const char *buff, const char *end, regex_t *var_re, regex_t *func_re, char endchar);
int append_to_filter_list(char ***list, int *count, int *alloced, const char *string);
const char *build_regex_string(const char **list, int count);
const char *walk_command(const char *p, const char *end, char endchar, const char interpret_level);


#define d1printf(expr...)		dprintf(1,expr)
#define d2printf(expr...)		dprintf(2,expr)
#define dprintf(level,expr...)		\
    if(debugging>=level)		\
	fprintf(stderr,expr);

static int debugging;

int
main(int argc, char *const *argv)
{
    FILE *file_in = NULL;
    FILE *file_out = NULL;
    char **funcs = NULL;	char **vars = NULL;
    char *file_buff=NULL;
    const char *end = NULL;
    int funcs_count = 0;	int vars_count = 0;
    int funcs_alloced = 0;	int vars_alloced = 0;
    int c;
    size_t  file_size=0, buff_alloced = 0;
    regex_t vre, *pvre=NULL;
    regex_t fre, *pfre=NULL;
    const char *fsr, *vsr;
    char *temp = NULL;
    struct stat st;
    debugging = 0;
    funcs = (char **)malloc(sizeof(char *)*10);
    vars = (char **)malloc(sizeof(char *)*10);
    if(funcs == NULL || vars == NULL) {
	fprintf(stderr,"failure allocing needed memory\n");
	exit(MEM_FAIL);
    }
    while((c = getopt(argc, argv, "i:f:v:d")) != EOF) {
//	fprintf(stderr,"c=%i\n",c);
	switch(c){
	case 'd':
	    debugging++;
	    break;
	case 'i':
	    if(file_in != NULL) {
		fprintf(stderr,"-i cannot be specified twice. bailing\n");
		exit(USAGE_FAIL);
	    }
	    if(stat(optarg, &st)){
		fprintf(stderr,"error stating file %s, bailing\n", optarg);
	        exit(IO_FAIL);
	    }
	    file_size=st.st_size;
	    file_in=fopen(optarg, "r");
	    if(file_in == NULL) {
		fprintf(stderr,"error opening file %s, bailing\n", optarg);
		exit(IO_FAIL);
	    }
	    break;
	case 'f':
//	    fprintf(stderr,"wassube.  opt_art=%s\n",optarg);
	    if(append_to_filter_list(&funcs, &funcs_count, &funcs_alloced,optarg)) {
		fprintf(stderr,"-f arg '%s', isn't valid.  must be comma delimited\n", 
		    optarg);
		exit(USAGE_FAIL);
	    }
	    break;
	case 'v':
	    if(append_to_filter_list(&vars, &vars_count, &vars_alloced,optarg)) {
		fprintf(stderr,"-v arg '%s', isn't valid.  must be comma delimited\n", optarg);
		exit(USAGE_FAIL);
	    }	   
	    break;
	default:
	    fprintf(stderr,"Usage [-i file] [-f func1,func2,func3 ] [-v func1,func2,func3 ]\n");
	    exit(USAGE_FAIL);
	}
    }
    if(file_size==0) {
	file_in = stdin;
    } else {
	fclose(stdin);
    }
    file_out = stdout;

    fsr = build_regex_string((const char **)funcs, funcs_count);
    d1printf("fsr buffer=%s\n", fsr);
    vsr = build_regex_string((const char **)vars, vars_count);
    d1printf("vsr buffer=%s\n", vsr);
    if(fsr) { 
	// prefix ^
	if((temp = (char *)malloc(strlen(fsr) + 3)) == NULL) {
	    fprintf(stderr, "failed allocing needed memory for regex patterns.\n");
	    exit(MEM_FAIL);
	}
	temp[0]='^'; temp[1] = '\0';
	temp = strcat(temp,fsr);
	temp = strcat(temp,"$");
	d1printf("fsr pattern is %s\n", temp);
	regcomp(&fre, temp, REG_EXTENDED);
	free(temp);	temp = NULL;
	pfre=&fre;
	free((void*)fsr);	fsr = NULL;
    } else
	pfre=NULL;
    if(vsr) {
	if((temp = (char *)malloc(strlen(vsr) + 3)) == NULL) {
	    fprintf(stderr, "failed allocing needed memory for regex patterns.\n");
	    exit(MEM_FAIL);
	}
	temp[0]='^'; temp[1] = '\0';
	temp = strcat(temp,vsr);
	temp = strcat(temp,"$");
	d1printf("vsr pattern is %s\n", temp);
	regcomp(&vre, temp, REG_EXTENDED);
	free(temp);	temp = NULL;
	pvre=&vre;
	free((void*)vsr);	vsr = NULL;
    } else
	pvre=NULL;
    

    if(file_size) {
	file_buff = (char *)malloc(file_size + 1);
	if(file_buff == NULL) {
	   fprintf(stderr, "failed allocing needed memory for file.\n");
	   exit(MEM_FAIL);
	}
	if(file_size != fread(file_buff, 1, file_size, file_in)) {
	   fprintf(stderr, "failed reading file\n");
	   exit(IO_FAIL);
	}
    } else {
	if((file_buff = (char *)malloc(4096)) == NULL) {
	    fprintf(stderr, "failed allocing needed memory for file.\n");
	    exit(MEM_FAIL);
	}
	buff_alloced = 4096;
	c=4096;
	while(c > 0) {
	    c=fread(file_buff+file_size, 1, 4096, file_in);
	    file_size += c;
	    // realloc +1 for null termination.
	    if(buff_alloced < file_size + 4096) {
 		if((file_buff = (char *)realloc(file_buff, buff_alloced + 4096)) == NULL) {
		    fprintf(stderr, "failed allocing needed memory for file.\n");
		    exit(MEM_FAIL);
		}
		buff_alloced += 4096;
	    }
	}
	d1printf("read %i bytes\n", file_size);
    }
    file_buff[file_size] = '\0';
    fclose(file_in);

    init_regexes();
    end=process_scope(file_out,file_buff, file_buff + file_size,pvre, pfre, '\0');
    d1printf("%i == %i\n", end - file_buff, file_size);

    fflush(file_out);
    fclose(file_out);
    free_regexes();
    free((void*)fsr);	free((void*)vsr);
    free(file_buff);
    exit(0);
}

int
append_to_filter_list(char ***list, int *count, int *alloced, const char *string)
{
   char *d = NULL;
   char **l = *list;
   char *s = NULL;
   s = strdup(string);
   d = strtok(s, ",");
   if(d == NULL)
	return 1;
   while(d != NULL) {
	if(*alloced == *count) {
	    if( (l=(char **)realloc(l, sizeof(char*) * (*alloced + 10))) == NULL) {
		return 1;
	    }
	    *alloced+=10;
	}
	l[*count] = d;
	(*count)++;
	d=strtok(NULL,",");
   }
   *list=l;
   return 0;
}

const char *
build_regex_string(const char **list, int count)
{
    char *buff, *p;
    const char *p2;
    int l = 0, x = 0, escaped = 0;

    for(x=0; x< count; x++) {
	l += strlen(list[x]) + 1;
	p2=list[x];
	// if it's ., substitute a [^ =] internally.
	while(*p2!='\0'){
	    if(*p2=='.')
		l+=4;
	    p2++;
	}
    }
    if(l == 0)
	return NULL;
    //shave off the extra '|' char, add in '(...)'.  hence, 3.
    buff = malloc(l + 5);
    memset(buff,0,l+4);
    buff[0] = '(';
    p=buff + 1;
    for(x=0; x < count; x++) {
	p2=list[x];
	escaped=0;
	while(*p2 != '\0') {
	    if(*p2=='.' && escaped==0) {
		strcat(p,"[^= ]");
		p += 4;
	    } else if(*p2 == '\\') {
		*p = *p2;
		p2++;    p++;
		if(escaped == 1)
		    escaped=0;
		else
		    escaped=1;
		continue;
	    } else {
		*p = *p2;
	    }
	    p++;
	    p2++;
	    escaped=0;
	}
	*p = '|';
	p++;
    }
    p[-1] = ')';
    p[0] = '\0';
    return buff;
}

regex_t func_r;
regex_t var_r;

void
init_regexes()
{
    regcomp(&func_r,"^(function[[:space:]]+|)([^\"'()=[:space:]]+)[[:space:]]*\\(\\)[[:space:]]*\\{",REG_EXTENDED);
    regcomp(&var_r,"^([^=[:space:]$(]+)=",REG_EXTENDED);
}
void
free_regexes()
{
    regfree(&func_r);
    regfree(&var_r);
}

/*    
fprintf(stderr,"REG_BADRPT:%i\nREG_BADBR:%i\nREG_EBRACE:%i\nREG_EBRACK:%i\nREG_ERANGE:%i\nREG_ECTYPE:%i\nREG_EPAREN:%i\nREG_ESUBREG:%i\nREG_EEND:%i\nREG_EESCAPE:%i\nREG_BADPAT:%i\nREG_ESIZE:%i\nREG_ESPACE:%i\n",
REG_BADRPT,REG_BADBR,REG_EBRACE,REG_EBRACK,REG_ERANGE,REG_ECTYPE,REG_EPAREN,REG_ESUBREG,REG_EEND,REG_EESCAPE,
REG_BADPAT,REG_ESIZE,REG_ESPACE);
*/

// zero for doesn't match, !0 for matches.
int
regex_matches(regex_t *re, const char *buff)
{
    regmatch_t match[1];
    match[0].rm_so = match[0].rm_eo = -1;
    assert(buff != NULL);
    assert(re != NULL);
    regexec(re, buff, 1, match, 0);
//    fprintf(stderr,"result was %i for %s, returning %i\n", match[0].rm_so, buff,i);
    return match[0].rm_so != -1 ? 1 : 0;
}

const char *
process_scope(FILE *out_fd, const char *buff, const char *end, regex_t *var_re, regex_t *func_re, char endchar)
{
    const char *p = NULL;
    const char *window_start = NULL, *window_end = NULL;
    const char *new_p = NULL;
    const char *com_start = NULL;
    const char *s = NULL, *e = NULL;
    char *temp_string = NULL;
    int x;

    regmatch_t	matches[3];
    p=buff;
    for(x=0; x < 3; x++)
	matches[x].rm_so = -1;

    window_start = buff;
    window_end = NULL;
    while(p < end && *p != endchar) {
	// wander forward to the next non space.
	if(window_end != NULL) {
	    if(out_fd != NULL)
		fwrite(window_start, window_end - window_start, 1, out_fd);
	    window_start = p;
	    window_end = NULL;
	}
	com_start = p;
	if(isspace(*p)) {
	   p++; continue;
	}
	// ignore comments
	if(*p == '#') {
	    while(p < end && *p != '\n') {
		p++;
	    }
//	    window_end = p;
	    continue;
	}
	// actual text.
	regexec(&func_r, p, 3, matches, 0);
	if(matches[0].rm_so != -1){
	    //got us a func match.
	    if(matches[2].rm_so != -1) {
		s = p + matches[2].rm_so;	e = p + matches[2].rm_eo;
	    } else {
		s = p;	e = p + matches[1].rm_eo;
	    }
	    temp_string = (char*)malloc(e - s + 1);
	    memset(temp_string,0,e - s + 1);
	    memcpy(temp_string,s, e - s);
	    d1printf("matched func name '%s'\n", temp_string);
	    //output it if it doesn't match.

	    new_p=process_scope(NULL,p + matches[0].rm_eo, end, NULL, NULL, '}');
	    d1printf("ended processing  '%s'\n", temp_string);
	    if(func_re!=NULL && regex_matches(func_re, temp_string)) {
		//well, it matched.  so it gets skipped.
		d1printf("filtering func '%s'\n", temp_string);
		window_end = com_start;
	    }

	    p = new_p;	
//	    p += matches[0].rm_eo;
	    free(temp_string);
	    temp_string = NULL;
	    for(x=0; x < 3; x++)
		matches[x].rm_so = -1;

	} else {
	    // check for env assignment
	    regexec(&var_r, p, 2, matches, 0);
	    if(matches[0].rm_so == -1) {
		//exactly as it sounds, non env assignment.
		p=walk_command(p,end,'\0',COMMAND_PARSING);
	    } else {
		//env assignment
		temp_string=(char*)malloc(matches[1].rm_eo + 1);
		memset(temp_string,0,matches[1].rm_eo + 1);
		memcpy(temp_string,p, matches[1].rm_eo);
		d1printf("matched env assign '%s'\n", temp_string);
		p += matches[0].rm_eo;
		for(x=0; x < 3; x++)
		    matches[x].rm_so = -1;

		if(p >= end)
		    return p;
		if('\''==*p)
		    p=walk_command(p + 1,end,*p,NO_PARSING);
		else if('"' == *p || '`' == *p)
		    p=walk_command(p + 1,end,*p,ESCAPED_PARSING);
		else if('(' == *p)
		    p=walk_command(p + 1,end,')',ESCAPED_PARSING);
		else if(isspace(*p)) {
		    while(p < end && isspace(*p) && *p != '\n')
			p++;
		} else if('$' == *p) {
		    if(p + 1 >= end) {
			p++;
			continue;
		    }
		    if('(' == p[1]) {
			p=walk_command(p + 2,end, ')',ESCAPED_PARSING);
		    } else if('\'' == p[1]) {
			p=walk_command(p + 2,end, '\'', DOLLARED_QUOTE_PARSING);
		    } else if('{' == p[1]) {
			p=walk_command(p + 2,end, '}', ESCAPED_PARSING);
		    } else {
			x=0;
			while(p < end && (!isspace(*p) || x)) {
			    if('\\' == *p)
				x=1;
			    else
				x=0;
			    p++;
			}
		    }
		    p++;
		} else {
		    // blah=cah ; single word.
		    p=walk_command(p + 1,end, ' ',SPACE_PARSING);
		}
		if(var_re!=NULL && regex_matches(var_re, temp_string)) {
		    //this would be filtered.
		    window_end = com_start;
		}
		free(temp_string);
		temp_string=NULL;
	    }
	}
	p++;
//	fprintf(stderr,"at byte %i of %i\n", p - buff, strchr(buff,'\0') - buff);
    }
//    fprintf(stderr, "returning %x\n", p);
    if(out_fd != NULL) {
	if(window_end == NULL)
	    window_end = p;
	if(window_end > end)
	    window_end = end;
	fwrite(window_start, window_end - window_start, 1,out_fd);
    }
    return p;
}

// interpret level == 0, no interprettation (no escaping), 1 == normal command limiting, 2 == wait strictly for 
// endchar
const char *
walk_command(const char *p, const char *end, char endchar, const char interpret_level)
{
    int escaped = 0;
    int dollared = 0;
    int here_count = 0;
    regex_t here_re;
    char *here_pattern;
    regmatch_t	match[1];
    char *temp_string = NULL;
    const char *end_here;
    int x;
    while(p < end) {
	if(*p == endchar || 
	   (interpret_level == COMMAND_PARSING && (';'==*p || '\n'==*p)) ||
	   (interpret_level == SPACE_PARSING && isspace(*p))) {
	    if(!escaped)
		return p;
	} else if(NO_PARSING==interpret_level) {
	    p++;
	    continue;
	} else if('\\' == *p && !escaped) {
	    escaped = 1;	p++;	continue;
	} else if(escaped) {
	    escaped = 0;
	} else if(DOLLARED_QUOTE_PARSING == interpret_level) {
	    p++;
	    continue;
	} else if('<' == *p) {
	    here_count++;
	    if(2 == here_count && interpret_level == COMMAND_PARSING) {
		p++;
		if(p >= end) {
		    fprintf(stderr, "bailing\n");
		    return p;
		}
		while(p < end && (isspace(*p) || '-' == *p))
		    p++;
		if('\'' == *p || '"' == *p) {
		    end_here = walk_command(p + 1,end,*p,NO_PARSING);
		    p++;
		} else {
		    end_here = walk_command(p,end,' ',SPACE_PARSING);
		}
//		d1printf("end_here=%.5s\n",end_here);
		d2printf("matched '%.*s' for a here word\n", end_here -p, p);
		temp_string = malloc(end_here -p + 1);
		memcpy(temp_string, p, end_here - p);
		temp_string[end_here - p] = '\0';
		// XXX watch this.  potential for horkage.  need to do the quote removal thing.
		//this sucks.

		end_here++;
		if(end_here >= end) {
		    return end_here;
		}
		end_here = bmh_search(temp_string, end_here, end - end_here);
		d1printf("bmh returned %i\n", end_here);
		if(end_here) {
		    d2printf("bmh = %.10s\n", end_here);
		    p=end_here + strlen(temp_string) -1 ;
		    d2printf("continuing on at %.10s\n", p);
		} else {
		    p = end;
		}
		free(temp_string);
		here_count = 0;
	    } else {
		d2printf("noticed '<', interpret_level=%i\n", interpret_level);
		p++; continue;
	    }
	} else if('$' == *p && !dollared && !escaped) {
	    dollared = 1;    p++;	continue;
	} else if('{' == *p) {
	    //process_scope.  this gets fun.
//	    fprintf(stderr,"process_scope called for %.10s\n", p - 10);
//	    p=process_scope(NULL,p+1,end,NULL,NULL,'}');
	    p=walk_command(p+1,end, '}', ESCAPED_PARSING);
	    // kind of a hack.
	} else if('(' == *p && interpret_level == COMMAND_PARSING) {
	    p=walk_command(p + 1, end, ')',ESCAPED_PARSING);
	} else if('`' == *p || '"' == *p) {
	    p=walk_command(p + 1, end, *p, ESCAPED_PARSING);
	} else if('\'' == *p && '"' != endchar) {
	    p=walk_command(p + 1, end, '\'', NO_PARSING);
	}
	p++;
	escaped=0;
	dollared=0;
    }
    return p;
}
