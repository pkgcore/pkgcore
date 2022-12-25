__econf_options_eapi8() {
	if [[ $1 == *"--datarootdir"* ]]; then
		echo "--datarootdir=${EPREFIX}/usr/share"
	fi
	if [[ $1 == *--enable-shared[^A-Za-z0-9+_.-]* && $1 == *--enable-static[^A-Za-z0-9+_.-]* ]]; then
		echo "--disable-static"
	fi
}
