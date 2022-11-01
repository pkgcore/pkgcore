__econf_options_eapi5() {
	if [[ $1 == *"--disable-silent-rules"* ]]; then
		echo --disable-silent-rules
	fi
}
