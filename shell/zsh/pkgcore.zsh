#!/usr/bin/env zsh
# Common library of useful shell functions leveraging pkgcore functionality.

# get an attribute for a given package
_pkgattr() {
	local pkg_attr=$1 pkg_atom=$2 repo=$3
	local -a pkg

	if [[ -z ${pkg_atom} ]]; then
		echo "Enter a valid package name." >&2
		return 1
	fi

	if [[ -n ${repo} ]]; then
		pkg=("${(@f)$(pquery -r "${repo}" --raw --unfiltered --cpv --one-attr "${pkg_attr}" -n -- "${pkg_atom}" 2>/dev/null)}")
	else
		pkg=("${(@f)$(pquery --ebuild-repos --raw --unfiltered --cpv --one-attr "${pkg_attr}" -n -- "${pkg_atom}" 2>/dev/null)}")
	fi
	if [[ $? != 0 ]]; then
		echo "Invalid package atom: '${pkg_atom}'" >&2
		return 1
	fi

	local choice
	if [[ -z ${pkg[@]} ]]; then
		echo "No matches found." >&2
		return 1
	elif [[ ${#pkg[@]} > 1 ]]; then
		echo "Multiple matches found:" >&2
		local p i=1
		for p in ${pkg[@]}; do
			echo "  ${i}: ${p%%:*}" >&2
			(( i++ ))
		done
		echo -n "Please select one: " >&2
		read choice
		if [[ ${choice} -lt 1 || ${choice} -gt ${#pkg} ]]; then
			echo "Invalid choice!" >&2
			exit 1
		fi
	else
		choice=1
	fi
	echo ${pkg[${choice}]#*:}
}

# cross-shell compatible PATH searching
_which() {
	whence -p "$1" >/dev/null
}
