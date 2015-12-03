# Common library of useful shell functions leveraging pkgcore functionality.
# Source this file from your .bashrc, .zshrc, or similar.
#
# Note that most functions currently use non-POSIX features so bash or zsh are
# basically required.

_pkgpath() {
	if [[ -z $1 ]]; then
		echo "Enter a valid package name." >&2
		return 1
	fi

	local -a pkg
	local p repo=$2

	if [[ -n ${repo} ]]; then
		pkg=( $(pquery -r "${repo}" --raw --unfiltered --cpv --one-attr path -n -- "$1" 2>/dev/null) )
	else
		pkg=( $(pquery --ebuild-repos --raw --unfiltered --cpv --one-attr path -n -- "$1" 2>/dev/null) )
	fi
	if [[ $? != 0 ]]; then
		echo "Invalid package atom: '$1'" >&2
		return 1
	fi

	if [[ -z ${pkg[@]} ]]; then
		echo "No matches found." >&2
		return 1
	elif [[ ${#pkg[@]} > 1 ]]; then
		echo "Multiple matches found:" >&2
		for p in ${pkg[@]}; do
			echo ${p%:*} >&2
		done
		return 1
	fi
	echo ${pkg#*:}
}

# change to a package directory
#
# usage: pcd pkg [repo]
# example: pcd sys-devel/gcc gentoo
#
# This will change the CWD to the sys-devel/gcc directory in the gentoo repo.
# Note that pkgcore's extended atom syntax is supported so one can also
# abbreviate the command to `pcd gcc gentoo` assuming there is only one package
# with a name of 'gcc' in the gentoo repo.
#
# Note that this should work for any local repo type on disk, e.g. one can also
# use this to enter the repos for installed or binpkgs via 'vdb' or 'binpkg'
# repo arguments, respectively.
pcd() {
	local pkgpath=$(_pkgpath "$@")
	[[ -z ${pkgpath} ]] && return 1

	# find the nearest parent directory
	while [[ ! -d ${pkgpath} ]]; do
		pkgpath=$(dirname "${pkgpath}")
	done

	pushd "${pkgpath}" >/dev/null
}
