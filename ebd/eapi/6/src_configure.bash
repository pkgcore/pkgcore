__econf_options_eapi6() {
	if [[ $1 == *"--docdir"* ]]; then
		echo --docdir="${EPREFIX}"/usr/share/doc/${PF}
	fi
	if [[ $1 == *"--htmldir"* ]]; then
		echo --htmldir="${EPREFIX}"/usr/share/doc/${PF}/html
	fi
}
