#include "elib.h"

const char * const atom_op_str[] = { "", ">", ">=", "=", "<=", "<", "~", "!", "!!", "*" };
const char * const version_suffixes_str[] = {"alpha", "beta", "pre", "rc", "p", ""};

version_suffixes getsuffix(const char *suff)
{
    size_t len = sizeof(version_suffixes_str) / sizeof(*version_suffixes_str);
    version_suffixes i;
    for (i = 0; i < len; ++i)
        if (!strncmp(suff, version_suffixes_str[i], 
                     strlen(version_suffixes_str[i])))
            return i;
}

/*
 * pms version comparison logic
 */
cmp_code version_cmp(const char *v1, const char *v2)
{
    if (!isvalid_version(v1) || !isvalid_version(v2))
        return ERROR;

    char *ptr1, *ptr2;
    unsigned long long n1 = strtoll(v1, &ptr1, 10);
    unsigned long long n2 = strtoll(v2, &ptr2, 10);
    if (n1 > n2)
        return 1;
    else if (n1 < n2)
        return -1;

    char c1, c2;
    while ((*ptr1 == '.') && (*ptr2 == '.')) {
        ++ptr1; ++ptr2;
        if (*ptr1 == '0' || *ptr2 == '0') {
            while (isdigit(*ptr1) || isdigit(*ptr2)) {
                c1 = isdigit(*ptr1) ? *ptr1++ : '0';
                c2 = isdigit(*ptr2) ? *ptr2++ : '0';
                if (c1 > c2)
                    return 1;
                else if (c1 < c2)
                    return -1;
            }
        } else {
            n1 = strtoll(ptr1, &ptr1, 10);
            n2 = strtoll(ptr2, &ptr2, 10);
            if (n1 > n2)
                return 1;
            else if (n1 < n2)
                return -1;
        }
    }
    if (*ptr1 == '.')
        return 1;
    else if (*ptr2 == '.')
        return -1;

    if (isalpha(*ptr1) && isalpha(*ptr2)) {
        if (*ptr1 > *ptr2)
            return 1;
        else if (*ptr1 < *ptr2)
            return -1;
        ++ptr1; ++ptr2;
    }
    else if (isalpha(*ptr1))
        return 1;
    else if (isalpha(*ptr2))
        return -1;

    while ((*ptr1 == '_') && (*ptr2 == '_')) {
        ++ptr1; ++ptr2;
        version_suffixes suff1 = getsuffix(ptr1);
        version_suffixes suff2 = getsuffix(ptr2);
        if (suff1 > suff2)
            return 1;
        else if (suff1 < suff2)
            return -1;
        else {
            ptr1 += strlen(version_suffixes_str[suff1]);
            ptr2 += strlen(version_suffixes_str[suff2]);
            n1 = strtoll(ptr1, &ptr1, 10);
            n2 = strtoll(ptr2, &ptr2, 10);
            if (n1 > n2)
                return 1;
            else if (n1 < n2)
                return -1;
        }
    }
    if (*ptr1 == '_')
        return getsuffix(ptr1 + 1) == SUF_P ? 1 : -1;
    else if (*ptr2 == '_')
        return getsuffix(ptr2 + 1) == SUF_P ? -1 : 1;

    n1 = (*ptr1 == '-') ? atoll(ptr1 + 2) : 0;
    n2 = (*ptr2 == '-') ? atoll(ptr2 + 2) : 0;
    if (n1 > n2)
        return 1;
    else if (n1 < n2)
        return -1;
    
    return 0;
}

/*
 * do versions match according to given operation ?
 */
int version_match(const char *v1, const char *v2, atom_op op)
{
    if (!isvalid_version(v1) || !isvalid_version(v2))
        return -1;

    cmp_code ret = version_cmp(v1, v2);

    switch (op) {
    case ATOM_OP_NEWER:
        return ret == NEWER;
    case ATOM_OP_NEWER_EQUAL:
        return ret != OLDER;
    case ATOM_OP_PV_EQUAL:
    case ATOM_OP_EQUAL:
        return ret == EQUAL;
    case ATOM_OP_OLDER_EQUAL:
        return ret != NEWER;
    case ATOM_OP_OLDER:
        return ret == OLDER;
    default:
        return 0;
    }
}

atom_op atom_op_from_str(const char *op)
{
    switch (op[0]) {
    case '!':
        ++op;
        if (op[0] == '!')
            return ATOM_OP_BLOCK_HARD;
        else
            return ATOM_OP_BLOCK;
    case '>':
        ++op;
        if (op[0] == '=')
            return ATOM_OP_NEWER_EQUAL;
        else
            return ATOM_OP_NEWER;
    case '=':
        return ATOM_OP_EQUAL;
    case '<':
        ++op;
        if (op[0] == '=')
            return ATOM_OP_OLDER_EQUAL;
        else
            return ATOM_OP_OLDER;
    case '~':
        return ATOM_OP_PV_EQUAL;
    default:
        return ATOM_OP_NONE;
    }
}
