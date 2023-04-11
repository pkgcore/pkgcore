__econf_options_eapi4() {
	if [[ $1 == *--disable-dependency-tracking[^A-Za-z0-9+_.-]* ]]; then
		echo --disable-dependency-tracking
	fi
}
