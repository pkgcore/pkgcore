source "${PKGCORE_EBD_PATH}"/eapi/4-phase.bash

__econf_options_eapi5() {
	if [[ $1 == *"--disable-silent-rules"* ]]; then
		echo --disable-silent-rules
	fi
}

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

has_version() { __query_version_funcs "$@"; }
best_version() { __query_version_funcs "$@"; }

usex() {
	use "$1" && echo "${2-yes}$4" || echo "${3-no}$5"
	return 0
}

:
