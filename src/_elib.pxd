cdef extern from "elib.h":

    const char * const atom_op_str[]
    int ebuild_errno

    ctypedef enum cmp_code:
        OLDER = -1
        EQUAL
        NEWER
        NOT_EQUAL
        ERROR

    ctypedef enum atom_op:
        ATOM_OP_NONE = 0
        ATOM_OP_NEWER
        ATOM_OP_NEWER_EQUAL
        ATOM_OP_EQUAL
        ATOM_OP_OLDER_EQUAL
        ATOM_OP_OLDER
        ATOM_OP_PV_EQUAL
        ATOM_OP_BLOCK
        ATOM_OP_BLOCK_HARD
        ATOM_OP_STAR

    ctypedef struct CPV:
        char *P
        char *PN
        char *PV
        unsigned long long PR_int
        char *PVR
        char *PF
        char *CATEGORY

    ctypedef struct ATOM:
        char *P
        char *PN
        char *PV
        unsigned long long PR_int
        char *PVR
        char *PF
        char *CATEGORY
        char *SLOT
        char *SUBSLOT
        char *REPO
        char **USE_DEPS
        atom_op pfx_op, sfx_op
        atom_op block_op

    CPV *cpv_alloc(const char *cpv_string, bint versioned)
    void cpv_free(CPV *cpv)
    cmp_code cpv_cmp(const CPV *cpv1, const CPV *cpv2)
    cmp_code cpv_cmp_str(const char *s1, const char *s2)
    const char *ebuild_strerror(int code)

    ATOM *atom_alloc(const char *atom_string)
    ATOM *atom_alloc_eapi(const char *atom_string, int eapi)
    void atom_free(ATOM *atom)
    cmp_code atom_cmp(const ATOM *atom1, const ATOM *atom2)
    cmp_code atom_cmp_str(const char *s1, const char *s2)
    int atom_intersect(const ATOM *atom1, const ATOM *atom2);
    int atom_intersect_str(const char *s1, const char *s2);
    int isvalid_eapi_reqs(const ATOM *atom, int eapi)
    const char *ebuild_strerror(int code)

    cmp_code version_cmp(const char *v1, const char *v2)
    int version_match(const char *v1, const char *v2, atom_op op)
    atom_op atom_op_from_str(const char *op);
