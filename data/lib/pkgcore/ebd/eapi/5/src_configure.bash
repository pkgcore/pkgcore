__econf_options_eapi5() {
	if [[ $1 == *--disable-silent-rules[^A-Za-z0-9+_.-]* ]]; then
		echo --disable-silent-rules
	fi
}
