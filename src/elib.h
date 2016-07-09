#ifndef COMMON_H
#define COMMON_H
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ctype.h>

#ifdef DOTS_DISALLOWED
#define VALID_CHAR(c) (isalnum(c) \
        || '-' == (c) \
        || '+' == (c) \
        || '_' == (c))
#else
#define VALID_CHAR(c) (isalnum(c) \
        || '-' == (c) \
        || '+' == (c) \
        || '_' == (c) \
        || '.' == (c))
#endif

#define VALID_USE_CHAR(c) (isalnum(c) \
        || '-' == (c) \
        || '+' == (c) \
        || '_' == (c) \
        || '@' == (c))

#define VALID_REPO_CHAR(c) (isalnum(c) \
        || '-' == (c) \
        || '_' == (c))

#define INVALID_FIRST_CHAR(c) (!VALID_CHAR(c) \
        || '-' == (c) \
        || '+' == (c) \
        || '.' == (c))

#define INVALID_FIRST_REPO_CHAR(c) (!VALID_REPO_CHAR(c) \
        || '-' == (c))

#define INVALID_FIRST_USE_CHAR(c) (!isalnum(c))
#define USEDEP_PREF(c) ((c) == '!' || (c) == '-')
#define USEDEP_SUF(c) ((c) == '=' || (c) == '?')

#define SLOT_OPERATOR(c) ((c) == '*' || (c) == '=')
#define VALID_EAPI(eapi) ((eapi) >= 0 && (eapi) <= 6)

typedef enum {
    E_OK=0,
    E_INVALID_CATEGORY,
    E_INVALID_CATEGORY_FIRST_CHAR,
    E_INVALID_PN,
    E_INVALID_PN_FIRST_CHAR,
    E_INVALID_PN_VERSIONED_SUF,
    E_INVALID_VERSION,
    E_INVALID_SLOT,
    E_INVALID_REPO,
    E_INVALID_USE_DEP,
    E_INVALID_EAPI,
    E_EAPI_LT2_ATOM_BLOCK_HARD,
    E_EAPI_EQ0_ATOM_SLOT,
    E_EAPI_LT2_ATOM_REPO,
    E_EAPI_LT5_ATOM_SLOT_OP_STAR,
    E_EAPI_LT5_ATOM_SLOT_OP_EQUAL,
    E_EAPI_LT5_ATOM_SUBSLOT,
    E_EAPI_LT2_ATOM_USE_DEPS,
    E_EAPI_LT4_ATOM_USE_DEPS_DEFAULT,
    E_INVALID_ATOM_OP_COMBO,
    E_INVALID_ATOM_OP_EMPTY_VER,
    E_INVALID_ATOM_OP_NONEMPTY_UNVER,
    E_INVALID_ATOM_OP_STAR_NEQ,
    E_NOMEM,
} eerror_t;

extern eerror_t ebuild_errno;
extern const char * const version_suffixes_str[6];
extern const char * const atom_op_str[10];

typedef enum { OLDER=-1, EQUAL, NEWER, NOT_EQUAL, ERROR } cmp_code;
typedef enum { SUF_ALPHA=0, SUF_BETA, SUF_PRE, SUF_RC, SUF_P, SUF_NORM } version_suffixes;
typedef enum {
    /*    */ ATOM_OP_NONE = 0,
    /* >  */ ATOM_OP_NEWER,
    /* >= */ ATOM_OP_NEWER_EQUAL,
    /* =  */ ATOM_OP_EQUAL,
    /* <= */ ATOM_OP_OLDER_EQUAL,
    /* <  */ ATOM_OP_OLDER,
    /* ~  */ ATOM_OP_PV_EQUAL,
    /* !  */ ATOM_OP_BLOCK,
    /* !! */ ATOM_OP_BLOCK_HARD,
    /* *  */ ATOM_OP_STAR,
} atom_op;

typedef struct {
    version_suffixes suffix;
    unsigned long val;
} suffix_ver;

typedef struct {
    char *P;
    char *PN;
    char *PV;
    unsigned long long PR_int;
    char *PVR;
    char *PF;
    char *CATEGORY;
    char letter; /* optional version letter */
    suffix_ver *suffixes;
} CPV;

typedef struct {
    char *P;
    char *PN;
    char *PV;
    unsigned long long PR_int;
    char *PVR;
    char *PF;
    char *CATEGORY;
    char *SLOT, *SUBSLOT;
    char *REPO;
    char **USE_DEPS; /* NULL as end indicator */
    char letter; /* optional version letter */
    suffix_ver *suffixes;
    atom_op pfx_op, sfx_op;
    atom_op block_op;
} ATOM;

/*
 * libebuild interface 
 ***/
CPV *cpv_alloc(const char *cpv_string, int versioned);
void cpv_free(CPV *cpv);
void cpv_print(const CPV *cpv);
cmp_code cpv_cmp(const CPV *cpv1, const CPV *cpv2);
cmp_code cpv_cmp_str(const char *s1, const char *s2);

ATOM *atom_alloc(const char *atom_string);
ATOM *atom_alloc_eapi(const char *atom_string, int eapi);
void atom_free(ATOM *atom);
void atom_print(const ATOM *atom);
cmp_code atom_cmp(const ATOM *atom1, const ATOM *atom2);
cmp_code atom_cmp_str(const char *s1, const char *s2);
int atom_intersect(const ATOM *atom1, const ATOM *atom2);
int atom_intersect_str(const char *s1, const char *s2);

cmp_code version_cmp(const char *v1, const char *v2);
int version_match(const char *v1, const char *v2, atom_op operation);
/***/

int isvalid_eapi_reqs(const ATOM *atom, int eapi);
int isvalid_version(const char *version);
int isvalid_usedep(const char *usedep);
int isvalid_repo(const char *repo);
int isvalid_slot(const char *slot);
version_suffixes getsuffix(const char *suff);
atom_op atom_op_from_str(const char *op);
const char *ebuild_strerror(eerror_t code);

#define set_ebuild_errno(code) ebuild_errno = (code)

#endif // COMMON_H
