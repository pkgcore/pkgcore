# Common library of shell functions for parsing various Gentoo-related data
# and leveraging pkgcore functionality.

# get an attribute for a given package
_pkgattr() {
	local pkg_attr=$1 pkg_atom=$2 repo=$3
	local -a pkg

	if [[ -z ${pkg_atom} ]]; then
		echo "Enter a valid package name." >&2
		return 1
	fi

	if [[ -n ${repo} ]]; then
		IFS=$'\n' pkg=( $(pquery -r "${repo}" --raw --unfiltered --cpv --one-attr "${pkg_attr}" -n -- "${pkg_atom}" 2>&1) )
	else
		IFS=$'\n' pkg=( $(pquery --ebuild-repos --raw --unfiltered --cpv --one-attr "${pkg_attr}" -n -- "${pkg_atom}" 2>&1) )
	fi
	if [[ $? != 0 ]]; then
		# show pquery error message
		echo "${pkg[-1]}" >&2
		return 1
	fi

	local choice
	if [[ -z ${pkg[@]} ]]; then
		echo "No matches found." >&2
		return 1
	elif [[ ${#pkg[@]} > 1 ]]; then
		echo "Multiple matches found:" >&2
		choice=$(_choose "${pkg[@]%%:*}")
		[[ $? -ne 0 ]] && return 1
	else
		choice=-1
	fi
	echo ${pkg[${choice}]#*:}
}

# cross-shell compatible PATH searching
_which() {
	type -P "$1" >/dev/null
}

# cross-shell compatible array index helper
# bash arrays start at 0
_array_index() {
	echo $1
}
