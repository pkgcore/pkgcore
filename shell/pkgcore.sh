# Common library of useful shell functions leveraging pkgcore functionality.
# Source this file from your .bashrc, .zshrc, or similar.
#
# Note that most functions currently use non-POSIX features so bash or zsh are
# basically required.

PKGSHELL=$(ps -p $$ -ocomm=)
if [[ ${PKGSHELL} != "bash" && ${PKGSHELL} != "zsh" ]]; then
	echo "pkgcore.sh: unsupported shell: ${PKGSHELL}" >&2
	return 1
fi

if [[ ${PKGSHELL} == "bash" ]]; then
	SCRIPTDIR=$(dirname ${BASH_SOURCE[0]})
else
	SCRIPTDIR=$(dirname ${(%):-%N})
fi
source "${SCRIPTDIR}"/${PKGSHELL}/pkgcore.${PKGSHELL}

export PATH=${SCRIPTDIR}/bin:${PATH}

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
	local pkgpath=$(_pkgattr path "$@")
	[[ -z ${pkgpath} ]] && return 1

	# find the nearest parent directory
	while [[ ! -d ${pkgpath} ]]; do
		pkgpath=$(dirname "${pkgpath}")
	done

	pushd "${pkgpath}" >/dev/null
}
