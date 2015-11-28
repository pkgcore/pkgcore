# Common library of useful shell functions leveraging pkgcore functionality.
# Source this file from your .bashrc, .zshrc, or similar.
#
# Note that most functions currently use non-POSIX features so bash or zsh are
# basically required.

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
	if [[ -z $1 || ${1:0:1} == "-" ]]; then
		echo "Enter a valid package name."
		return 1
	fi
	repo=$2

	local pkg p dirpath

	if [[ -n ${repo} ]]; then
		pkg=( $(pquery -r "${repo}" --raw "$1" --cpv --one-attr path -n) )
	else
		pkg=( $(pquery --ebuild-repos --raw "$1" --cpv --one-attr path -n) )
	fi
	[[ $? != 0 ]] && return 1

	if [[ -z ${pkg} ]]; then
		echo "No matches found."
		return 1
	elif [[ ${#pkg} > 1 ]]; then
		echo "Multiple matches found:"
		for p in ${pkg}; do
			echo ${p%:*}
		done
		return 1
	fi

	# find the nearest parent directory
	dirpath=${pkg#*:}
	while [[ ! -d ${dirpath} ]]; do
		dirpath=$(dirname "${dirpath}")
	done

	pushd "${dirpath}"
}
