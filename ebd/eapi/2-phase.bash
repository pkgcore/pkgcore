source "${PKGCORE_EBD_PATH}"/eapi/1-phase.bash

# define default phase functions -- only available in the related phases
__phase_funcs_pkg_nofetch_eapi2() {
	default_pkg_nofetch() { __phase_pkg_nofetch; }
}
__phase_funcs_src_unpack_eapi2() {
	default_src_unpack() { __phase_src_unpack; }
}
__phase_funcs_src_prepare_eapi2() {
	default_src_prepare() { __phase_src_prepare; }
}
__phase_funcs_src_configure_eapi2() {
	default_src_configure() { __phase_src_configure; }
}
__phase_funcs_src_compile_eapi2() {
	default_src_compile() { __phase_src_compile; }
}
__phase_funcs_src_test_eapi2() {
	default_src_test() { __phase_src_test; }
}

default() {
	if __is_function default_pkg_${EBUILD_PHASE}; then
		default_pkg_${EBUILD_PHASE}
	elif __is_function default_src_${EBUILD_PHASE}; then
		default_src_${EBUILD_PHASE}
	else
		die "default is not available in ebuild phase '${EBUILD_PHASE}'"
	fi
}

:
