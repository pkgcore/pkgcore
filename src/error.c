#include "elib.h"
eerror_t ebuild_errno = E_OK;

const char *ebuild_strerror(eerror_t code)
{
    switch (code) {
    case E_OK:
        return "No error";
    case E_INVALID_CATEGORY:
        return "Invalid category name";
    case E_INVALID_CATEGORY_FIRST_CHAR:
        return "Invalid first char in category name, should be alnum and not start with [-+.]";
    case E_INVALID_PN:
        return "Invalid package name";
    case E_INVALID_PN_FIRST_CHAR:
        return "Invalid first char in package name, should be alnum and not start with [-+.]";
    case E_INVALID_PN_VERSIONED_SUF:
        return "Invalid package name, shouldn't end with a valid version";
    case E_INVALID_VERSION:
        return "Invalid version";
    case E_INVALID_SLOT:
        return "Invalid slot";
    case E_INVALID_REPO:
        return "Invalid repo name";
    case E_INVALID_USE_DEP:
        return "Invalid use dependency";
    case E_INVALID_EAPI:
        return "Invalid eapi";
    case E_EAPI_LT2_ATOM_BLOCK_HARD:
        return "Atom strong block prefix isn't allowed for EAPI < 2";
    case E_EAPI_EQ0_ATOM_SLOT:
        return "Atom slot isn't allowed for EAPI 0";
    case E_EAPI_LT2_ATOM_REPO:
        return "Atom repo isn't allowed for EAPI < 2";
    case E_EAPI_LT5_ATOM_SLOT_OP_STAR:
        return "Atom slot star[*] operation isn't allowed for EAPI < 5";
    case E_EAPI_LT5_ATOM_SLOT_OP_EQUAL:
        return "Atom slot equal[= | slot=] operation isn't allowed for EAPI < 5";
    case E_EAPI_LT5_ATOM_SUBSLOT:
        return "Atom subslot isn't allowed for EAPI < 5";
    case E_EAPI_LT2_ATOM_USE_DEPS:
        return "Atom use deps aren't allowed for EAPI < 2";
    case E_EAPI_LT4_ATOM_USE_DEPS_DEFAULT:
        return "Atom use deps defaults aren't allowed for EAPI < 4";
    case E_INVALID_ATOM_OP_COMBO:
        return "Invalid atom operations combination";
    case E_INVALID_ATOM_OP_EMPTY_VER:
        return "Empty operation for versioned atom isn't allowed";
    case E_INVALID_ATOM_OP_NONEMPTY_UNVER:
        return "Operation for unversioned atom should be empty";
    case E_INVALID_ATOM_OP_STAR_NEQ:
        return "Atom glob postfix[*] may be combined only with equal[=] prefix";
    case E_NOMEM:
        return "No memory error";
    default:
        return "Unknown error";
    }
}
