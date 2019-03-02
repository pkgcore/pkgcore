__econf_options_eapi4() {
	if [[ $1 == *"--disable-dependency-tracking"* ]]; then
		echo --disable-dependency-tracking
	fi
}
