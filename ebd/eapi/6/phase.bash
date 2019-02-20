PKGCORE_BANNED_FUNCS+=( einstall )

__econf_options_eapi6() {
	if [[ $1 == *"--docdir"* ]]; then
		echo --docdir="${EPREFIX}"/usr/share/doc/${PF}
	fi
	if [[ $1 == *"--htmldir"* ]]; then
		echo --htmldir="${EPREFIX}"/usr/share/doc/${PF}/html
	fi
}

in_iuse() { [[ $1 =~ ${PKGCORE_IUSE_EFFECTIVE} ]]; }

get_libdir() { __get_libdir lib; }

einstalldocs() {
	local docs PKGCORE_DOCDESTTREE=
	if ! docs=$(declare -p DOCS 2> /dev/null); then
		for docs in README* ChangeLog AUTHORS NEWS TODO CHANGES \
				THANKS BUGS FAQ CREDITS CHANGELOG; do
			if [[ -s ${docs} ]]; then
				dodoc "${docs}" || return $?
			fi
		done
	elif [[ ${docs} == "declare -a "* ]]; then
		if [[ ${#DOCS[@]} -gt 0 ]]; then
			dodoc -r "${DOCS[@]}" || return $?
		fi
	elif [[ -n ${DOCS} ]]; then
		dodoc -r ${DOCS} || return $?
	fi

	PKGCORE_DOCDESTTREE=html
	if ! docs=$(declare -p HTML_DOCS 2> /dev/null); then
		:
	elif [[ ${docs} == "declare -a "* ]]; then
		if [[ ${#HTML_DOCS[@]} -gt 0 ]]; then
			dodoc -r "${HTML_DOCS[@]}" || return $?
		fi
	elif [[ -n ${HTML_DOCS} ]]; then
		dodoc -r ${HTML_DOCS} || return $?
	fi

	return 0
}

:
