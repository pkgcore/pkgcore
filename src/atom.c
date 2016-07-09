#include "elib.h"
#define atom_error(atom_ptr, code) \
    do { \
        set_ebuild_errno(code); \
        atom_free(atom_ptr); \
        return NULL; \
    } while(0)

void atom_print(const ATOM *atom)
{
    if (!atom) {
        printf("NULL\n");
        return;
    }
    printf("P: %s\n", atom->P);
    printf("PN: %s\n", atom->PN);
    printf("PV: %s\n", atom->PV);
    printf("PR: %lld\n", atom->PR_int);
    printf("PVR: %s\n", atom->PVR);
    printf("PF: %s\n", atom->PF);
    printf("CATEGORY: %s\n", atom->CATEGORY);
    printf("letter: %c\n", atom->letter);
    printf("suffixes: ");
    int i;
    for (i = 0; atom->suffixes[i].suffix != SUF_NORM; ++i) {
        printf("%s", version_suffixes_str[atom->suffixes[i].suffix]);
        printf("%lu ", atom->suffixes[i].val);
    }
    printf("\n");
    printf("SLOT: %s\n", atom->SLOT);
    printf("SUBSLOT: %s\n", atom->SUBSLOT);
    printf("REPO: %s\n", atom->REPO);
    printf("USE_DEPS: ");
    for (i = 0; atom->USE_DEPS[i]; ++i)
        printf("%s ", atom->USE_DEPS[i]);
    printf("\n");
    printf("block_op: %s\n", atom_op_str[atom->block_op]);
    printf("pfx_op: %s\n", atom_op_str[atom->pfx_op]);
    printf("sfx_op: %s\n", atom_op_str[atom->sfx_op]);
}

ATOM *atom_alloc(const char* atom_string)
{
    ATOM *ret;
    char *ptr, *tmp_ptr, *end_ptr;
    size_t m_len, atom_len, atom_string_len;
    int id, sid, sid_len;
    ebuild_errno = E_OK;

    // ATOM + P + PF + PVR + (CATEGORY,PN,PV,PR,SLOT,SUBSLOT,REPO,USE_DEPS)
    atom_len = sizeof(ATOM);
    atom_string_len = strlen(atom_string) + 1;
    m_len = atom_len + atom_string_len * 4;

    ret = malloc(m_len);
    if (ret == NULL)
        atom_error(ret, E_NOMEM);
    memset(ret, 0, m_len);

    ptr = (char*)ret;
    ret->P = ptr + atom_len;
    ret->PF = ret->P + atom_string_len;
    ret->PVR = ret->PF + atom_string_len;
    ret->CATEGORY = ret->PVR + atom_string_len;
    
    // set trailing usedeps element
    id = 0;
    ret->USE_DEPS = realloc(ret->USE_DEPS, sizeof(char*) * (id + 1));
    ret->USE_DEPS[id++] = NULL;

    if (atom_string[0] == '!') {
        ++atom_string;
        --atom_string_len;
        if (atom_string[0] == '!') {
            ++atom_string;
            --atom_string_len;
            ret->block_op = ATOM_OP_BLOCK_HARD;
        } else
            ret->block_op = ATOM_OP_BLOCK;
    } else
        ret->block_op = ATOM_OP_NONE;

    switch (atom_string[0]) {
    case '>':
        ++atom_string;
        --atom_string_len;
        if (atom_string[0] == '=') {
            ++atom_string;
            --atom_string_len;
            ret->pfx_op = ATOM_OP_NEWER_EQUAL;
        } else
            ret->pfx_op = ATOM_OP_NEWER;
        break;
    case '=':
        ++atom_string;
        --atom_string_len;
        ret->pfx_op = ATOM_OP_EQUAL;
        break;
    case '<':
        ++atom_string;
        --atom_string_len;
        if (atom_string[0] == '=') {
            ++atom_string;
            --atom_string_len;
            ret->pfx_op = ATOM_OP_OLDER_EQUAL;
        } else
            ret->pfx_op = ATOM_OP_OLDER;
        break;
    case '~':
        ++atom_string;
        --atom_string_len;
        ret->pfx_op = ATOM_OP_PV_EQUAL;
        break;
    default:
        ret->pfx_op = ATOM_OP_NONE;
        break;
    }
    strcpy(ret->CATEGORY, atom_string);
    end_ptr = ret->CATEGORY + atom_string_len - 2;

    // usedeps
    if (*end_ptr == ']')
        if (ptr = strchr(ret->CATEGORY, '[')) {
            *ptr++ = '\0';
            while ((tmp_ptr = strchr(ptr, ',')) ||
                  ((tmp_ptr = end_ptr) >= ptr)) {
                *tmp_ptr = '\0';
                if (!isvalid_usedep(ptr))
                    atom_error(ret, E_INVALID_USE_DEP);
                ret->USE_DEPS = realloc(ret->USE_DEPS, sizeof(char*) * (id + 1));
                ret->USE_DEPS[id - 1] = ptr;
                ret->USE_DEPS[id] = NULL;
                ptr = tmp_ptr + 1;
                ++id;
            }
            end_ptr = ret->USE_DEPS[0] - 2;
        } else
            atom_error(ret, E_INVALID_PN);

    // repo
    if (ptr = strstr(ret->CATEGORY, "::")) {
        ret->REPO = ptr + 2;
        *ptr = '\0';
        end_ptr = ptr - 1;
        if (!isvalid_repo(ret->REPO))
            atom_error(ret, E_INVALID_REPO);
    } else
        ret->REPO = end_ptr + 1;

    // slot
    if (ptr = strrchr(ret->CATEGORY, ':')) {
        ret->SLOT = ptr + 1;
        *ptr = '\0';
        end_ptr = ptr - 1;
        if (!isvalid_slot(ret->SLOT))
            atom_error(ret, E_INVALID_SLOT);
        if (ptr = strchr(ret->SLOT, '/')) {
            ret->SUBSLOT = ptr + 1;
            *ptr = '\0';
        } else
            ret->SUBSLOT = end_ptr + 1;
    } else {
        ret->SLOT = end_ptr + 1;
        ret->SUBSLOT = end_ptr + 1;
    }

    // match any base version
    if (*end_ptr == '*') {
        if (ret->pfx_op != ATOM_OP_EQUAL)
            atom_error(ret, E_INVALID_ATOM_OP_STAR_NEQ);
        ret->sfx_op = ATOM_OP_STAR;
        *end_ptr = '\0';
        end_ptr--;
    } else
        ret->sfx_op = ATOM_OP_NONE;
    
    // category
    ptr = ret->CATEGORY;
    if (INVALID_FIRST_CHAR(*ptr))
        atom_error(ret, E_INVALID_CATEGORY_FIRST_CHAR);
    while (*++ptr != '/')
        if (!VALID_CHAR(*ptr))
           atom_error(ret, E_INVALID_CATEGORY);

    *ptr = '\0';
    ret->PN = ptr + 1;
    if (INVALID_FIRST_CHAR(*(ret->PN)))
        atom_error(ret, E_INVALID_PN_FIRST_CHAR);
    strcpy(ret->PF, ret->PN);

    // version
    ptr = end_ptr;
    ret->PV = end_ptr + 1;
    while (ptr > ret->PN) {
        if (ptr[0] == '-' && isdigit(ptr[1])) {
            tmp_ptr = ptr;
            ret->PV = &ptr[1];
            break;
        }
        ptr--;
    }

    // set default suffix
    id = 0;
    ret->suffixes = realloc(ret->suffixes, sizeof(suffix_ver) * (id + 1));
    if (ret->suffixes == NULL)
        atom_error(ret, E_NOMEM);
    ret->suffixes[id].suffix = SUF_NORM;
    ret->suffixes[id].val = 0;

    if (ret->pfx_op == ATOM_OP_NONE) {
        if (ptr != ret->PN && isvalid_version(ret->PV))
            atom_error(ret, E_INVALID_ATOM_OP_EMPTY_VER);
        // set empty version
        ret->P   = end_ptr + 1;
        ret->PV  = end_ptr + 1;
        ret->PVR = end_ptr + 1;
    } else if (!isvalid_version(ret->PV)) {
        atom_error(ret, E_INVALID_VERSION);
    } else {
        // got a valid version along with prefix operator
        end_ptr = NULL;

        // revision
        if (ptr = strchr(ret->PV, '-')) {
            ret->PR_int = atoll(&ptr[2]);
            if (ret->PR_int) {
                strcpy(ret->PVR, ret->PV);
                ptr[0] = '\0';
            } else {
                ptr[0] = '\0';
                strcpy(ret->PVR, ret->PV);
            }
            end_ptr = ptr - 1;
        } else
            strcpy(ret->PVR, ret->PV);

        strcpy(ret->P, ret->PN);
        *tmp_ptr = '\0';

        // optional version letter
        if (ptr = strchr(ret->PV, '_')) {
            if (isalpha(ptr[-1]))
                ret->letter = ptr[-1];
        } else if (end_ptr) {
            if (isalpha(*end_ptr))
                ret->letter = *end_ptr;
        } else if ((end_ptr = &ret->PV[strlen(ret->PV)-1]) && (isalpha(*end_ptr)))
            ret->letter = *end_ptr;

        // suffixes
        while (ptr && *ptr) {
            if (!(tmp_ptr = strchr(&ptr[1], '_')))
                tmp_ptr = ptr + strlen(ptr);

            sid = getsuffix(&ptr[1]);
            ret->suffixes[id].suffix = sid;
            sid_len = strlen(version_suffixes_str[sid]);
            ptr += sid_len;

            char num[tmp_ptr - ptr];
            strncpy(num, &ptr[1], tmp_ptr - ptr - 1);
            num[tmp_ptr - ptr] = '\0';
            ret->suffixes[id].val = atoll(num);

            id++;
            ret->suffixes = realloc(ret->suffixes, sizeof(suffix_ver) * (id + 1));
            if (ret->suffixes == NULL)
                err("Out of memory error\n");
            ret->suffixes[id].suffix = SUF_NORM;
            ret->suffixes[id].val = 0;

            ptr = tmp_ptr;
        }
    }

    ptr = ret->PN;
    while (*++ptr)
        if (!VALID_CHAR(*ptr))
            atom_error(ret, E_INVALID_PN);
        // pkgname shouldn't end with a hyphen followed by a valid version
        else if (ptr[0] == '-' && isdigit(ptr[1]) && isvalid_version(&ptr[1]))
            atom_error(ret, E_INVALID_PN_VERSIONED_SUF);

    return ret;
}

ATOM *atom_alloc_eapi(const char* atom_string, int eapi)
{
    ATOM *ret = atom_alloc(atom_string);
    if (!ret)
        return NULL;

    if (!isvalid_eapi_reqs(ret, eapi)) {
        atom_free(ret);
        return NULL;
    }

    return ret;
}

void atom_free(ATOM *atom)
{
    if (!atom) return;
    free(atom->USE_DEPS);
    free(atom->suffixes);
    free(atom);
}

/*
 * NOTE: unversioned atom implicitly gets 0 version
 * TODO: maybe this should be stronger?
 */
cmp_code atom_cmp(const ATOM *a1, const ATOM *a2)
{
    if (!a1 || !a2)
        return ERROR;

    if (strcmp(a1->CATEGORY, a2->CATEGORY)
        || strcmp(a1->PN, a2->PN)
        || strcmp(a1->SLOT, a2->SLOT)
        || strcmp(a1->SUBSLOT, a2->SUBSLOT)
        || strcmp(a1->REPO, a2->REPO))
        return NOT_EQUAL;
    
    // take atom [*] and [~] into account
    const char *v1, *v2;
    if (a1->pfx_op == ATOM_OP_PV_EQUAL || a2->pfx_op == ATOM_OP_PV_EQUAL) {
        v1 = a1->PV;
        v2 = a2->PV;
    } else {
        v1 = a1->PVR;
        v2 = a2->PVR;
    }

    if (a1->sfx_op == ATOM_OP_STAR || a2->sfx_op == ATOM_OP_STAR) {
        int len1, len2;
        len1 = strlen(v1);
        len2 = strlen(v2);

        if (len1 < len2 && a1->sfx_op == ATOM_OP_STAR)
            return strncmp(v1, v2, len1);
        else if (len2 < len1 && a2->sfx_op == ATOM_OP_STAR)
            return strncmp(v1, v2, len2);
    }
    return version_cmp(v1, v2);
}

cmp_code atom_cmp_str(const char *s1, const char *s2)
{
    cmp_code ret;
    char *ptr;
    ATOM *a1, *a2;

    if (!(a1 = atom_alloc(s1)))
        return ERROR;

    if (!(a2 = atom_alloc(s2)))
        goto atom_error;

    ret = atom_cmp(a1, a2);

    atom_free(a2);
atom_error:
    atom_free(a1);
    return ret;
}

/*
 * do atoms intersect ?
 * blockers doesn't count
 * use deps only count if atoms have opposite state of the flag
 */
int atom_intersect(const ATOM *a1, const ATOM *a2)
{
    if (!a1 || !a2)
        return -1;

    // only cares in case property presented in both
    if (strcmp(a1->CATEGORY, a2->CATEGORY)
        || strcmp(a1->PN, a2->PN)
        || (*a1->SLOT && *a2->SLOT && strcmp(a1->SLOT, a2->SLOT))
        || (*a1->SUBSLOT && *a2->SUBSLOT && strcmp(a1->SUBSLOT, a2->SUBSLOT))
        || (*a1->REPO && *a2->REPO && strcmp(a1->REPO, a2->REPO)))
        return 0;

    // check if atoms have the same use flag enabled and disabled
    if (*a1->USE_DEPS && *a2->USE_DEPS) {
        int i, j;
        for (i = 0; a1->USE_DEPS[i]; ++i)
            if (a1->USE_DEPS[i][0] == '-') {
                for (j = 0; a2->USE_DEPS[j]; ++j)
                    if (!strcmp(&a1->USE_DEPS[i][1], a2->USE_DEPS[j]))
                        return 0;
            } else if (a1->USE_DEPS[i][0] != '!')
                for (j = 0; a2->USE_DEPS[j]; ++j)
                    if (a2->USE_DEPS[j][0] == '-' &&
                        !strcmp(a1->USE_DEPS[i], &a2->USE_DEPS[j][1]))
                        return 0;
    }

    if (!*a1->PVR || !*a2->PVR)
        return 1;

#define NEWER_OP(a) ((a)->pfx_op == ATOM_OP_NEWER || \
                     (a)->pfx_op == ATOM_OP_NEWER_EQUAL)
#define OLDER_OP(a) ((a)->pfx_op == ATOM_OP_OLDER || \
                     (a)->pfx_op == ATOM_OP_OLDER_EQUAL)

    /*
     * [>|>=] [>|>=] or [<|<=] [<|<=]
     * [~] [~]
     * [*] [*]
     * [~] [*]   or [*] [~]
     * [=] [any] or [any] [=]
     * [>|>=] [<|<=] or [<|<=] [>|>=]
     * [>|>=|<|<=] [~] or [~] [>|>=|<|<=]
     * [>|>=|<|<=] [*] or [*] [>|>=|<|<=]
     **/

    // both have the same direction
    if ((NEWER_OP(a1) && NEWER_OP(a2)) ||
        (OLDER_OP(a1) && OLDER_OP(a2)))
        return 1;

    const char *v1, *v2;
    if (a1->pfx_op == ATOM_OP_PV_EQUAL || a2->pfx_op == ATOM_OP_PV_EQUAL) {
        v1 = a1->PV;
        v2 = a2->PV;
    } else {
        v1 = a1->PVR;
        v2 = a2->PVR;
    }

    // both version or revision globs
    if (a1->sfx_op == ATOM_OP_STAR && a2->sfx_op == ATOM_OP_STAR)
        return !strncmp(v1, v2, strlen(v1)) ||
               !strncmp(v1, v2, strlen(v2));
    if (a1->pfx_op == ATOM_OP_PV_EQUAL && a2->pfx_op == ATOM_OP_PV_EQUAL)
        return version_match(v1, v2, a2->pfx_op);

    // one version glob, other revision glob
    if (a1->sfx_op == ATOM_OP_STAR && a2->pfx_op == ATOM_OP_PV_EQUAL)
        return !strncmp(v1, v2, strlen(v1));
    if (a2->sfx_op == ATOM_OP_STAR && a1->pfx_op == ATOM_OP_PV_EQUAL)
        return !strncmp(v1, v2, strlen(v2));

    // one is exactly equal
    if (a1->pfx_op == ATOM_OP_EQUAL && a1->sfx_op != ATOM_OP_STAR)
        if (a2->sfx_op == ATOM_OP_STAR)
            return !strncmp(v1, v2, strlen(v2));
        else
            return version_match(v1, v2, a2->pfx_op);
    if (a2->pfx_op == ATOM_OP_EQUAL && a2->sfx_op != ATOM_OP_STAR)
        if (a1->sfx_op == ATOM_OP_STAR)
            return !strncmp(v1, v2, strlen(v1));
        else
            return version_match(v2, v1, a1->pfx_op);

    const ATOM *ranged, *other;
    if (NEWER_OP(a1) || OLDER_OP(a1)) {
        ranged = a1;
        other  = a2;
    } else {
        ranged = a2;
        other  = a1;
        const char *tmp = v1;
        v1 = v2; v2 = tmp;
    }

    // have the opposite direction
    if (NEWER_OP(other) || OLDER_OP(other))
        return version_match(v1, v2, other->pfx_op) &&
               version_match(v2, v1, ranged->pfx_op);

    if (other->pfx_op == ATOM_OP_PV_EQUAL)
        return version_match(v2, v1, ranged->pfx_op);

    // is it worth it ? whatever, let's conquer it all
    if (other->sfx_op == ATOM_OP_STAR) {
        if (version_match(v2, v1, ranged->pfx_op))
            return 1;

        // find if it's possible to make our glob version bigger/less
        if (NEWER_OP(ranged)) {
            // can make by adding up to revision
            if (ranged->PR_int && other->PR_int)
                return !version_cmp(ranged->PV, other->PV);
            else if (other->PR_int)
                return 0;

            // only can do bigger in cases like:
            // =c/p-4.1_alpha10* >=c/p-4.10_alpha101,
            // =c/p-4.1_alpha10*  >c/p-4.10_alpha10,
            // =c/p-4.1_alpha* >=c/p-4.10_alpha10_p1
            // =c/p-4.1_alpha10* >c/p-4.10_alpha10_p1
            if (ranged->suffixes[0].suffix != SUF_NORM &&
                other->suffixes[0].suffix  != SUF_NORM) {
                char *rptr = strchr(v1, '_');
                char *optr = strchr(v2, '_');
                int len1 = rptr - v1;
                int len2 = optr - v2;
                char rv[len1 + 1];
                char ov[len2 + 1];
                strncpy(rv, v1, len1); rv[len1] = '\0';
                strncpy(ov, v2, len2); ov[len2] = '\0';
                if (version_cmp(rv, ov))
                    return 0;

                int i;
                for (i = 0; ranged->suffixes[i].suffix != SUF_NORM &&
                            other->suffixes[i].suffix != SUF_NORM; ++i)
                    if (ranged->suffixes[i].suffix > other->suffixes[i].suffix)
                        return 0;
                    else if (ranged->suffixes[i].val > other->suffixes[i].val)
                        return ((other->suffixes[i+1].suffix == SUF_NORM) &&
                                (ranged->suffixes[i+1].suffix == SUF_NORM ||
                                 ranged->suffixes[i+1].suffix == SUF_P));
                    else if (ranged->suffixes[i].val == other->suffixes[i].val)
                        if (other->suffixes[i+1].suffix == SUF_NORM)
                            return 1;

                return (ranged->suffixes[i].suffix == SUF_NORM &&
                        other->suffixes[i].suffix == SUF_NORM);

            } else if (other->suffixes[0].suffix != SUF_NORM)
                return 0;

            // only can handle cases like:
            // =c/p-4.1a* >=c/p-4.1a_p1,
            // =c/p-4.1a* >=c/p-4.1a-r10
            // otherwise can't do bigger
            if (other->letter)
                return !strncmp(v1, v2, strlen(v2));

            // can do bigger in case only last numeric component
            // of glob version doesn't match
            char *optr = strrchr(v2, '.');
            if (optr)
                return !strncmp(v1, v2, optr - v2);
            else
                return 1;
        } else {
            // can do less by adding some extra suffixes
            if (other->PR_int)
                return 0;
            return !strncmp(v1, v2, strlen(v2));
        }
    }
#undef NEWER_OP
#undef OLDER_OP
}

int atom_intersect_str(const char *s1, const char *s2)
{
    int ret;
    char *ptr;
    ATOM *a1, *a2;

    if (!(a1 = atom_alloc(s1)))
        return -1;

    if (!(a2 = atom_alloc(s2)))
        goto atom_error;

    ret = atom_intersect(a1, a2);

    atom_free(a2);
atom_error:
    atom_free(a1);
    return ret;
}

#undef atom_error
