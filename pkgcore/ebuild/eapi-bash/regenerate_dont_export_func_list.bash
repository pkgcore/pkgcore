#!/bin/bash

_FP="${1:-dont_export_funcs.list}"

export PKGCORE_BIN_PATH=$(dirname "$0")
if [[ -z ${PKGCORE_CLEAN_ENV} ]]; then
	exec env -i PKGCORE_PYTHON_PATH="${PKGCORE_PYTHON_PATH}" PKGCORE_CLEAN_ENV=1 /bin/bash "$0" "${_FP}"
fi

export LC_ALL=C # avoid any potential issues of unicode sorting for whacked func names
# export this so that scripts will behave as libs
export PKGCORE_SOURCING_FOR_REGEN_FUNCS_LIST=1
set -f # shell expansion can bite us in the ass during the echo below
cd "${PKGCORE_BIN_PATH}" || { echo "!!! failed cd'ing to ${PKGCORE_BIN_PATH}" >&2; exit 1; }

# force some ordering.

__source_was_seen() {
	local x
	for x in "${seen[@]}"; do
		[[ $x == $1 ]] && return 0
	done
	return 1
}
declare -a seen
source() {
	local fp=$(readlink -f "$1")
	__source_was_seen "$fp" && return 0
	# die relies on these vars; we reuse them.
	local CATEGORY=${PKGCORE_BIN_PATH}
	local PF=$1
	echo "sourcing ${x}" >&2
	. "$@" || { echo "!!! failed sourcing ${x}; exit $?" >&2; exit 3; }
	seen[${#seen[@]}]="${fp}"
	return 0
}

# without this var, parsing certain things can fail; force tot true
# so any code that tried accessing it thinks it succeeded
export PKGCORE_PYTHON_BINARY=/bin/true

forced_order_source="isolated-functions.lib exit-handling.lib eapi/common.lib ebuild-daemon.lib ebuild-daemon.bash"

for x in ${forced_order_source} $(find . -name '*.lib' | sed -e 's:^\./::' | sort); do
	source "${x}"
done

# wipe our custom funcs
unset __source_was_seen
unset source

echo >&2

# Sorting order; put PMS functionality first, then our internals.
result=$(__environ_list_funcs | sort)
result=$(echo "$result" | grep -v "^__"; echo "$result" | grep "^__")
if [[ "${_FP}" == '-' ]]; then
	echo "$result"
else
	echo "$result" > dont_export_funcs.list
fi
