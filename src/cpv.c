#include "elib.h"
#define cpv_error(cpv_ptr, code) \
    do { \
        set_ebuild_errno(code); \
        cpv_free(cpv_ptr); \
        return NULL; \
    } while(0)

void cpv_print(const CPV *cpv)
{
    if (!cpv) {
        printf("NULL\n");
        return;
    }
    printf("P: %s\n", cpv->P);
    printf("PN: %s\n", cpv->PN);
    printf("PV: %s\n", cpv->PV);
    printf("PR: %lld\n", cpv->PR_int);
    printf("PVR: %s\n", cpv->PVR);
    printf("PF: %s\n", cpv->PF);
    printf("CATEGORY: %s\n", cpv->CATEGORY);
    printf("letter: %c\n", cpv->letter);
    printf("suffixes: ");
    int i;
    for (i = 0; cpv->suffixes[i].suffix != SUF_NORM; ++i) {
        printf("%s", version_suffixes_str[cpv->suffixes[i].suffix]);
        printf("%lu ", cpv->suffixes[i].val);
    }
    printf("\n");
}

static CPV *cpv_alloc_versioned(const char *cpv_string)
{
    CPV *ret;
    char *ptr, *tmp_ptr, *end_ptr;
    size_t m_len, cpv_len, cpv_string_len;
    int id, sid, sid_len;
    ebuild_errno = E_OK;

    // CPV + P + PF + PVR + (CATEGORY,PN,PV,PR)
    cpv_len = sizeof(CPV);
    cpv_string_len = strlen(cpv_string) + 1;
    m_len = cpv_len + cpv_string_len * 4;

    ret = malloc(m_len);
    if (ret == NULL)
        cpv_error(ret, E_NOMEM);
    memset(ret, 0, m_len);

    ptr = (char*)ret;
    ret->P = ptr + cpv_len;
    ret->PF = ret->P + cpv_string_len;
    ret->PVR = ret->PF + cpv_string_len; 
    ret->CATEGORY = ret->PVR + cpv_string_len;
    strcpy(ret->CATEGORY, cpv_string);

    // category
    ptr = ret->CATEGORY;
    end_ptr = ptr + cpv_string_len - 2;
    if (INVALID_FIRST_CHAR(*ptr))
        cpv_error(ret, E_INVALID_CATEGORY_FIRST_CHAR);
    while (*++ptr != '/')
        if (!VALID_CHAR(*ptr))
            cpv_error(ret, E_INVALID_CATEGORY);

    *ptr = '\0';
    ret->PN = ptr + 1;
    if (INVALID_FIRST_CHAR(*(ret->PN)))
        cpv_error(ret, E_INVALID_PN_FIRST_CHAR);
    strcpy(ret->PF, ret->PN);

    tmp_ptr = NULL;
    ptr = end_ptr;
    ret->PV = end_ptr + 1;
    ret->PR_int = 0;
 
    // version
    while (ptr > ret->PN) {
        if (ptr[0] == '-' && isdigit(ptr[1])) {
            end_ptr = ptr;
            ret->PV = &ptr[1];
            break;
        }
        ptr--;
    }
    if (!isvalid_version(ret->PV))
        cpv_error(ret, E_INVALID_VERSION);
    else {
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
            tmp_ptr = ptr - 1;
        } else
            strcpy(ret->PVR, ret->PV);
        strcpy(ret->P, ret->PN);
        *end_ptr = '\0';
    }

    ptr = ret->PN;
    while (*++ptr)
        if (!VALID_CHAR(*ptr))
            cpv_error(ret, E_INVALID_PN);
        // pkgname shouldn't end with a hyphen followed by a valid version
        else if (ptr[0] == '-' && isdigit(ptr[1]) && isvalid_version(&ptr[1]))
            cpv_error(ret, E_INVALID_PN_VERSIONED_SUF);

    // optional version letter
    if (ptr = strchr(ret->PV, '_')) {
        if (isalpha(ptr[-1]))
            ret->letter = ptr[-1];
    } else if (tmp_ptr) {
        if (isalpha(*tmp_ptr))
            ret->letter = *tmp_ptr;
    } else if ((tmp_ptr = &ret->PV[strlen(ret->PV)-1]) && (isalpha(*tmp_ptr)))
        ret->letter = *tmp_ptr;

    // suffixes
    id = 0;
    ret->suffixes = realloc(ret->suffixes, sizeof(suffix_ver) * (id + 1));
    if (ret->suffixes == NULL)
        cpv_error(ret, E_NOMEM);
    ret->suffixes[id].suffix = SUF_NORM;
    ret->suffixes[id].val = 0;

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
            cpv_error(ret, E_NOMEM);
        ret->suffixes[id].suffix = SUF_NORM;
        ret->suffixes[id].val = 0;

        ptr = tmp_ptr;
    }

    return ret;
}

static CPV *cpv_alloc_unversioned(const char *cpv_string)
{
    CPV *ret;
    char *ptr, *tmp_ptr;
    size_t m_len, cpv_len, cpv_string_len;
    ebuild_errno = E_OK;

    // CPV + PF + (CATEGORY,PN)
    cpv_len = sizeof(CPV);
    cpv_string_len = strlen(cpv_string) + 1;
    m_len = cpv_len + cpv_string_len * 2;

    ret = malloc(m_len);
    if (ret == NULL)
        cpv_error(ret, E_NOMEM);
    memset(ret, 0, m_len);

    ptr = (char*)ret;
    ret->PF = ptr + cpv_len;
    ret->CATEGORY = ret->PF + cpv_string_len;
    strcpy(ret->CATEGORY, cpv_string);

    ptr = ret->CATEGORY;
    // set empty version
    ret->P = ptr + cpv_string_len - 1;
    ret->PV = ret->P;
    ret->PR_int = 0;
    ret->PVR = ret->P;

    // category
    if (INVALID_FIRST_CHAR(*ptr))
        cpv_error(ret, E_INVALID_CATEGORY);
    while (*++ptr != '/')
        if (!VALID_CHAR(*ptr))
            cpv_error(ret, E_INVALID_CATEGORY);

    *ptr = '\0';
    ret->PN = ptr + 1;
    if (INVALID_FIRST_CHAR(*(ret->PN)))
        cpv_error(ret, E_INVALID_PN);
    strcpy(ret->PF, ret->PN);

    ptr = ret->PN;
    while (*++ptr)
        if (!VALID_CHAR(*ptr))
            cpv_error(ret, E_INVALID_PN);
        // pkgname shouldn't end with a hyphen followed by a valid version
        else if (ptr[0] == '-' && isdigit(ptr[1]) && isvalid_version(&ptr[1]))
            cpv_error(ret, E_INVALID_PN_VERSIONED_SUF);

    ret->suffixes = malloc(sizeof(suffix_ver));
    if (ret->suffixes == NULL)
        cpv_error(ret, E_NOMEM);
    ret->suffixes[0].suffix = SUF_NORM;
    ret->suffixes[0].val = 0;

    return ret;
}

CPV *cpv_alloc(const char *cpv_string, int versioned)
{
    if (versioned)
        return cpv_alloc_versioned(cpv_string);
    else
        return cpv_alloc_unversioned(cpv_string);
}

void cpv_free(CPV *cpv)
{
    if (!cpv) return;
    free(cpv->suffixes);
    free(cpv);
}

cmp_code cpv_cmp(const CPV *c1, const CPV *c2)
{
    if (!c1 || !c2)
        return ERROR;

    int ret;
    if (ret = strcmp(c1->CATEGORY, c2->CATEGORY))
        return ret > 0 ? NEWER : OLDER;
    if (ret = strcmp(c1->PN, c2->PN))
        return ret > 0 ? NEWER : OLDER;
    if (!*c1->PVR) {
        if (!*c2->PVR)
            return EQUAL;
        else
            return OLDER;
    } else if (!*c2->PVR)
        return NEWER;
    return version_cmp(c1->PVR, c2->PVR);
}

cmp_code cpv_cmp_str(const char *s1, const char *s2)
{
    cmp_code ret;
    char *ptr;
    CPV *c1, *c2;

    if (!(c1 = cpv_alloc(s1, 1)))
        c1 = cpv_alloc(s1, 0);
    if (!c1)
        return ERROR;

    if (!(c2 = cpv_alloc(s2, 1)))
        c2 = cpv_alloc(s2, 0);
    if (!c2)
        goto cpv_error;

    ret = cpv_cmp(c1, c2);

    cpv_free(c2);
cpv_error:
    cpv_free(c1);
    return ret;
}

#undef cpv_error
