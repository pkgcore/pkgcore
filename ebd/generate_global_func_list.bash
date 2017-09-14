#!/usr/bin/env bash
#
# Generate the list of globally defined functions.
#
# This script is run dynamically in a repo or tarball layout on initialization
# of the build environment. For installed versions, a static function list is
# generated at install time and used instead.

export PKGCORE_EBD_PATH=${BASH_SOURCE[0]%/*}

# re-exec ourselves inside an empty environment
if [[ -z ${PKGCORE_CLEAN_ENV} ]]; then
	exec env -i \
		PKGCORE_PYTHON_BINARY="${PKGCORE_PYTHON_BINARY}" \
		PKGCORE_PYTHONPATH="${PKGCORE_PYTHONPATH}" \
		PATH="${PATH}" \
		PKGCORE_CLEAN_ENV=1 \
		"$0" "$@"
fi

# avoid any potential issues of unicode sorting for whacked func names
export LC_ALL=C
DEBUG=false

while getopts ":d" opt; do
	case $opt in
		d) DEBUG=true ;;
		*) ;;
	esac
done

# use seen array to only source files once
declare -A seen
source() {
	local fp=$(readlink -f "$1")
	${seen[${fp}]:-false} && return 0
	# die relies on these vars; we reuse them.
	local CATEGORY=${PKGCORE_EBD_PATH}
	local PF=$1
	${DEBUG} && echo "sourcing ${x}" >&2
	. "$@" || { echo "!!! failed sourcing ${x}; exit $?" >&2; exit 3; }
	seen[${fp}]=true
	return 0
}

# Without this var, parsing certain things can fail; force to true if unset or
# null so any code that tried accessing it thinks it succeeded.
export PKGCORE_PYTHON_BINARY=${PKGCORE_PYTHON_BINARY:-/bin/true}

# proper sourcing order to satisfy dependencies
forced_order_source=(
	isolated-functions.lib
	exit-handling.lib
	eapi/depend.lib
	eapi/common.lib
	ebuild-daemon.lib
	ebuild-daemon.bash
)

# prefix all paths with ebd directory
forced_order_source=( "${forced_order_source[@]/#/${PKGCORE_EBD_PATH}\/}" )

# Source everything that requires a certain order first, then reload all libs
# including any ones that were skipped the first time.
#
# EAPI specific libs are skipped since those need be sourced on demand
# depending on an ebuild's EAPI.
for x in "${forced_order_source[@]}" "${PKGCORE_EBD_PATH}"/*.lib; do
	source "${x}"
done

# wipe our custom funcs
unset -f source

${DEBUG} && echo >&2
# Sorting order; put PMS functionality first, then our internals.
printf '%s\n' $(compgen -X '__*' -A function) $(compgen -A function __)
