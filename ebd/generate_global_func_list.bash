#!/usr/bin/env bash
#
# Generate the list of globally defined functions.
#
# This script is run dynamically in a repo or tarball layout on initialization
# of the build environment. For installed versions, a static function list is
# generated at install time and used instead.

export PKGCORE_EBD_PATH=$(dirname "$0")

if [[ -z ${PKGCORE_CLEAN_ENV} ]]; then
	exec env -i \
		PKGCORE_PYTHON_BINARY="${PKGCORE_PYTHON_BINARY}" \
		PKGCORE_PYTHONPATH="${PKGCORE_PYTHONPATH}" \
		PATH="${PATH}" \
		PKGCORE_CLEAN_ENV=1 \
		"$0" "$@"
fi

export LC_ALL=C # avoid any potential issues of unicode sorting for whacked func names
# export this so that scripts will behave as libs
export PKGCORE_SOURCING_FOR_REGEN_FUNCS_LIST=1
DEBUG=false

while getopts ":d" opt; do
	case $opt in
		d) DEBUG=true ;;
		*) ;;
	esac
done

# force some ordering
__source_was_seen() {
	local x
	for x in "${seen[@]}"; do
		[[ ${x} == $1 ]] && return 0
	done
	return 1
}
declare -a seen
source() {
	local fp=$(readlink -f "$1")
	__source_was_seen "${fp}" && return 0
	# die relies on these vars; we reuse them.
	local CATEGORY=${PKGCORE_EBD_PATH}
	local PF=$1
	${DEBUG} && echo "sourcing ${x}" >&2
	. "$@" || { echo "!!! failed sourcing ${x}; exit $?" >&2; exit 3; }
	seen[${#seen[@]}]=${fp}
	return 0
}

# Without this var, parsing certain things can fail; force to true if unset or
# null so any code that tried accessing it thinks it succeeded.
export PKGCORE_PYTHON_BINARY=${PKGCORE_PYTHON_BINARY:-/bin/true}

forced_order_source="isolated-functions.lib exit-handling.lib eapi/depend.lib eapi/common.lib ebuild-daemon.lib ebuild-daemon.bash"

# EAPI specific libs are skipped since those need be sourced on demand
# depending on an ebuild's EAPI.
pushd "${PKGCORE_EBD_PATH}" >/dev/null
for x in ${forced_order_source} *.lib; do
	source "${PKGCORE_EBD_PATH}/${x}"
done
popd >/dev/null

# wipe our custom funcs
unset -f __source_was_seen
unset -f source

# Sorting order; put PMS functionality first, then our internals.
result=$(compgen -A function | sort)
result=$(echo "${result}" | grep -v "^__"; echo "${result}" | grep "^__")

${DEBUG} && echo >&2
echo "${result}"
