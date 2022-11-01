__econf_options_eapi8() {
	if [[ $1 == *"--datarootdir"* ]]; then
		echo "--datarootdir=${EPREFIX}/usr/share"
	fi
	if [[ $1 == *"--disable-static"* || $1 == *"--enable-static"* ]]; then
		echo "--disable-static"
	fi
}
