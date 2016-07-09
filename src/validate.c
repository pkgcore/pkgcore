#include "elib.h"

int isvalid_eapi_reqs(const ATOM *atom, int eapi)
{
    ebuild_errno = E_OK;
    
    if (!VALID_EAPI(eapi)) {
        set_ebuild_errno(E_INVALID_EAPI);
        return 0;
    }

    if (atom->block_op == ATOM_OP_BLOCK_HARD && eapi < 2)
        set_ebuild_errno(E_EAPI_LT2_ATOM_BLOCK_HARD);
    else if (*atom->SLOT && eapi == 0)
        set_ebuild_errno(E_EAPI_EQ0_ATOM_SLOT);
    else if (*atom->REPO && eapi < 2)
        set_ebuild_errno(E_EAPI_LT2_ATOM_REPO);
    else if (*atom->SLOT == '*' && eapi < 5)
        set_ebuild_errno(E_EAPI_LT5_ATOM_SLOT_OP_STAR);
    else if ((strchr(atom->SLOT, '=') || strchr(atom->SUBSLOT, '=')) && eapi < 5)
        set_ebuild_errno(E_EAPI_LT5_ATOM_SLOT_OP_EQUAL);
    else if (*atom->SUBSLOT && eapi < 5)
        set_ebuild_errno(E_EAPI_LT5_ATOM_SUBSLOT);
    else if (*atom->USE_DEPS && eapi < 2)
        set_ebuild_errno(E_EAPI_LT2_ATOM_USE_DEPS);

    int i;
    for (i = 0; atom->USE_DEPS[i]; ++i)
        if (strchr(atom->USE_DEPS[i], '(') && eapi < 4) {
            set_ebuild_errno(E_EAPI_LT4_ATOM_USE_DEPS_DEFAULT);
            break;
        }
    if (ebuild_errno)
        return 0;
    return 1;
}

int isvalid_version(const char *ptr)
{
    int tmp;
    if (!isdigit(*ptr))
        return 0;
    while (isdigit(*++ptr))
        ;

    while (ptr[0] == '.' && isdigit(ptr[1]))
        while (isdigit(*++ptr))
            ;

    if (isalpha(*ptr)) // optional version letter
        if (!isalpha(ptr[1]) && islower(ptr[0]))
            ++ptr;
        else
            return 0;

    while (ptr[0] == '_' && (tmp = strlen(version_suffixes_str[getsuffix(&ptr[1])]))) {
        ptr += tmp + 1;
        while (isdigit(*ptr)) //optional suffix integer
            ++ptr;
    }
    if (ptr[0] == '-' && ptr[1] == 'r' && isdigit(ptr[2])) {
        ptr += 2;
        while (isdigit(*ptr))
            ++ptr;
    }

    return !*ptr;
}

int isvalid_usedep(const char *ptr)
{
    char pfx = 0;

    if (USEDEP_PREF(*ptr)) {
        pfx = *ptr;
        ++ptr;
    }
    if (INVALID_FIRST_USE_CHAR(*ptr))
        return 0;

    ++ptr;
    while (VALID_USE_CHAR(*ptr))
        ++ptr;
    if (ptr[0] == '(' && (ptr[1] == '+' || ptr[1] == '-') && ptr[2] == ')')
        ptr += 3;

    if (USEDEP_SUF(*ptr)) {
        if (pfx != '-')
            ++ptr;
    } else if (pfx == '!')
        return 0;

    return !*ptr; 
}

int isvalid_repo(const char *ptr)
{
    if (INVALID_FIRST_REPO_CHAR(*ptr))
        return 0;
    ++ptr;
    while (VALID_REPO_CHAR(*ptr))
        ++ptr;
    
    return !*ptr;
}

int isvalid_slot(const char *ptr)
{
    if (INVALID_FIRST_CHAR(*ptr))
        if (SLOT_OPERATOR(*ptr))
            return !ptr[1];
        else
            return 0;
    ++ptr;
    while (VALID_CHAR(*ptr))
        ++ptr;
    if (ptr[0] == '/' && !INVALID_FIRST_CHAR(ptr[1]))
        ptr += 2;

    while (VALID_CHAR(*ptr))
        ++ptr;
    if (*ptr == '=')
        ++ptr;

    return !*ptr;
}
