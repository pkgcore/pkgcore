PKGCORE_BANNED_FUNCS=( hasq hasv useq )

usev() {
	if use "$1"; then
		echo "${2:-${1#!}}"
		return 0
	fi
	return 1
}
