__phase_src_install() {
	if [[ -f Makefile || -f GNUmakefile || -f makefile ]]; then
		emake DESTDIR="${D}" install
	fi

	local docs PKGCORE_DOCDESTTREE=
	if ! docs=$(declare -p DOCS 2> /dev/null); then
		for docs in README* ChangeLog AUTHORS NEWS TODO CHANGES \
				THANKS BUGS FAQ CREDITS CHANGELOG; do
			[[ -s ${docs} ]] && dodoc "${docs}"
		done
	elif [[ ${docs} == "declare -a "* ]]; then
		dodoc "${DOCS[@]}"
	else
		dodoc ${DOCS}
	fi
}

:
