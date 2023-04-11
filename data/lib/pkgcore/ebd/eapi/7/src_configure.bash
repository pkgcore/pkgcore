__econf_options_eapi7() {
	if [[ $1 == *--with-sysroot[^A-Za-z0-9+_.-]* ]]; then
		echo --with-sysroot="${ESYSROOT:-/}"
	fi
}

:
