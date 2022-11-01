usex() {
	use "$1" && echo "${2-yes}$4" || echo "${3-no}$5"
	return 0
}

:
