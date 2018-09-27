# Copyright: 2012 Brian Harring <ferringb@gmail.com>
# license GPL2/BSD 3

source "${PKGCORE_EBD_PATH}"/eapi/4.bash

__query_version_funcs() {
	local atom root=${ROOT:-/}
	if [[ $1 == "--host-root" ]]; then
		root=/
		shift
	fi

	atom=$1
	shift
	[[ $# -gt 0 ]] && die "${FUNCNAME[1]}: unknown argument(s): $*"

	PKGCORE_DISABLE_COMPAT=true __portageq "${FUNCNAME[1]}" "${atom}" --domain-at-root "${root}"
}

has_version() {
	__query_version_funcs "$@"
}

best_version() {
	__query_version_funcs "$@"
}

usex() {
	use "$1" && echo "${2-yes}$4" || echo "${3-no}$5"
	return 0
}

# parallel tests are allowed (no forced -j1)
__phase_src_test() {
	addpredict /
	local extra_args=( ${EXTRA_EMAKE} )
	if make check -n &> /dev/null; then
		echo ">>> Test phase [check]: ${CATEGORY}/${PF}"
		emake "${extra_args[@]}" check || die "Make check failed. See above for details."
	elif make test -n &> /dev/null; then
		emake "${extra_args[@]}" test || die "Make test failed. See above for details."
	else
		echo ">>> Test phase [none]: ${CATEGORY}/${PF}"
	fi
	SANDBOX_PREDICT=${SANDBOX_PREDICT%:/}
}

:
