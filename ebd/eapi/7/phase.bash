PKGCORE_BANNED_FUNCS+=( libopts )

__econf_options_eapi7() {
	if [[ $1 == *"--with-sysroot"* ]]; then
		echo --with-sysroot="${ESYSROOT:-/}"
	fi
}

__query_version_funcs() {
	local atom root

	# default to root settings for -r option
	if ${PKGCORE_PREFIX_SUPPORT}; then
		root=${EROOT}
	else
		root=${ROOT}
	fi

	case $1 in
		-r) shift ;;
		-d)
			if ${PKGCORE_PREFIX_SUPPORT}; then
				root=${ESYSROOT}
			else
				root=${SYSROOT}
			fi
			shift ;;
		-b)
			if ${PKGCORE_PREFIX_SUPPORT}; then
				root=/${EPREFIX}
			else
				root=/
			fi
			shift ;;
	esac

	atom=$1
	shift
	[[ $# -gt 0 ]] && die "${FUNCNAME[1]}: unknown argument(s): $*"

	PKGCORE_DISABLE_COMPAT=true __portageq "${FUNCNAME[1]}" "${atom}" --domain-at-root "${root}"
}

:
