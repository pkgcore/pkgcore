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
