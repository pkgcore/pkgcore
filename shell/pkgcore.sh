# Common library of useful shell functions leveraging pkgcore functionality.
# Source this file from your .bashrc, .zshrc, or similar.
#
# Only bash and zsh are currently supported.

# determine interactive parent shell
PKGSHELL=$(ps -p $$ -ocomm=)
if [[ ${PKGSHELL} != "bash" && ${PKGSHELL} != "zsh" ]]; then
	echo "pkgcore.sh: unsupported shell: ${PKGSHELL}" >&2
	return 1
fi

# determine the directory path where this script exists
if [[ ${PKGSHELL} == "bash" ]]; then
	SCRIPTDIR=$(dirname $(realpath ${BASH_SOURCE[0]}))
else
	SCRIPTDIR=${${(%):-%x}:A:h}
fi

# source bash/zsh specific support
source "${SCRIPTDIR}"/${PKGSHELL}/pkgcore.${PKGSHELL}
export PATH=${SCRIPTDIR}/bin:${PATH}
unset PKGSHELL SCRIPTDIR

# interactively choose a value from an array
#
# usage: _choose "${array[@]}"
# returns: index of array choice (assuming array indexing starts at 1)
_choose() {
	local choice num_opts=$#

	# show available choices
	local x i=0
	for x in $@; do
		echo "  $(( ++i )): ${x}" >&2
	done

	# read user choice, checking for invalid values
	local invalid=0
	while true; do
		echo -n "Please select one: " >&2
		choice=$(_read_nchars ${#num_opts})
		if [[ ! ${choice} =~ [0-9]+ || ${choice} -lt 1 || ${choice} -gt ${num_opts} ]]; then
			(( invalid++ ))
			echo " -- Invalid choice!" >&2
			# three invalids seen, giving up
			[[ ${invalid} -gt 2 ]] && break
			continue
		fi
		echo >&2
		break
	done

	# default to array indexes starting at 0
	(( choice-- ))
	echo $(_array_index ${choice})
}

# change to a package directory
#
# This will change the current working directory to the sys-devel/gcc directory
# in the gentoo repo. Note that pkgcore's extended atom syntax is supported so
# one can also abbreviate the command to `pcd gcc gentoo` assuming there is
# only one package with a name of 'gcc' in the gentoo repo. In the case where
# multiple matches are found the list of choices is returned to select from.
#
# This should work for any local repo type on disk, e.g. one can also use this
# to enter the repos for installed or binpkgs via 'vdb' or 'binpkg' repo
# arguments, respectively.
pcd() {
	if [[ $1 == "-h" || $1 == "--help" ]]; then
		cat <<-EOF
			pcd: change to a package directory
			usage: pcd pkg [repo]
			example: pcd gcc gentoo -- change to the sys-devel/gcc directory in the gentoo repo
			example: pcd coreutils vdb -- change to the sys-apps/coreutils dir in the vdb
		EOF
		return 0
	fi

	local pkgpath=$(_pkgattr path "$@")
	[[ -z ${pkgpath} ]] && return 1

	# find the nearest parent directory
	while [[ ! -d ${pkgpath} ]]; do
		pkgpath=$(dirname "${pkgpath}")
	done

	pushd "${pkgpath}" >/dev/null
}
