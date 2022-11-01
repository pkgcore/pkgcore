__econf_options_eapi7() {
	if [[ $1 == *"--with-sysroot"* ]]; then
		echo --with-sysroot="${ESYSROOT:-/}"
	fi
}

:
