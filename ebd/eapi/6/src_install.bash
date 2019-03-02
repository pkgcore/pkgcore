PKGCORE_BANNED_FUNCS=( einstall )

einstalldocs() {
	local docs PKGCORE_DOCDESTTREE=
	if ! docs=$(declare -p DOCS 2> /dev/null); then
		local -a DOCS
		for docs in README* ChangeLog AUTHORS NEWS TODO CHANGES \
				THANKS BUGS FAQ CREDITS CHANGELOG; do
			[[ -s ${docs} ]] && DOCS+=( ${docs} )
		done
		if [[ ${#DOCS[@]} -gt 0 ]]; then
			dodoc "${DOCS[@]}" || return $?
		fi
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
