__econf_options_eapi5() {
	if [[ $1 == *"--disable-silent-rules"* ]]; then
		echo --disable-silent-rules
	fi
}

usex() {
	use "$1" && echo "${2-yes}$4" || echo "${3-no}$5"
	return 0
}

:
