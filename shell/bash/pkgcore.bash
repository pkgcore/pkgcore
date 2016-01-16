#!/usr/bin/env bash
# Common library of useful shell functions leveraging pkgcore functionality.

# get an attribute for a given package
_pkgattr() {
	local pkg_attr=$1 pkg_atom=$2 repo=$3 p
	local -a pkg

	if [[ -z ${pkg_atom} ]]; then
		echo "Enter a valid package name." >&2
		return 1
	fi

	if [[ -n ${repo} ]]; then
		IFS=$'\n' pkg=( $(pquery -r "${repo}" --raw --unfiltered --cpv --one-attr "${pkg_attr}" -n -- "${pkg_atom}" 2>/dev/null) )
	else
		IFS=$'\n' pkg=( $(pquery --ebuild-repos --raw --unfiltered --cpv --one-attr "${pkg_attr}" -n -- "${pkg_atom}" 2>/dev/null) )
	fi
	if [[ $? != 0 ]]; then
		echo "Invalid package atom: '${pkg_atom}'" >&2
		return 1
	fi

	if [[ -z ${pkg[@]} ]]; then
		echo "No matches found." >&2
		return 1
	elif [[ ${#pkg[@]} > 1 ]]; then
		echo "Multiple matches found:" >&2
		for p in ${pkg[@]}; do
			echo ${p%%:*} >&2
		done
		return 1
	fi
	echo ${pkg#*:}
}

# cross-shell compatible PATH searching
_which() {
	type -P "$1" >/dev/null
}
