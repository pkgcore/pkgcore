source "${PKGCORE_EBD_PATH}"/eapi/3-phase.bash

__econf_options_eapi4() {
	if [[ $1 == *"--disable-dependency-tracking"* ]]; then
		echo --disable-dependency-tracking
	fi
}

__phase_funcs_src_install_eapi4() {
	default_src_install() { __phase_src_install; }

	docompress() {
		if [[ $1 == "-x" ]]; then
			shift
			PKGCORE_DOCOMPRESS_SKIP+=( "$@" )
		else
			PKGCORE_DOCOMPRESS+=( "$@" )
		fi
	}
}

nonfatal() { PKGCORE_NONFATAL=true "$@"; }

:
