#!/bin/bash
export PKGCORE_BIN_PATH=$(dirname "$0")
if [[ -z ${PKGCORE_CLEAN_ENV} ]]; then
	exec env -i PKGCORE_PYTHON_PATH="${PKGCORE_PYTHON_PATH}" PKGCORE_CLEAN_ENV=1 /bin/bash "$0"
fi
export LC_ALL=C # avoid any potential issues of unicode sorting for whacked func names
set -f # shell expansion can bite us in the ass during the echo below
cd "${PKGCORE_BIN_PATH}" || { echo "!!! failed cd'ing to ${PKGCORE_BIN_PATH}" >&2; exit 1; }

pkgcore_initial_funcs=$(declare -F | cut -d ' ' -f3)

# force some ordering.

source_was_seen() {
	local x
	for x in "${seen[@]}"; do
		[[ $x == $1 ]] && return 0
	done
	return 1
}
declare -a seen
source() {
	local fp=$(readlink -f "$1")
	source_was_seen "$fp" && return 0
	# die relies on these vars; we reuse them.
	local CATEGORY=${PKGCORE_BIN_PATH}
	local PF=$1
	echo "sourcing ${x}" >&2
	. "$@" || { echo "!!! failed sourcing ${x}; exit $?" >&2; exit 3; }
	seen[${#seen[@]}]="${fp}"
	return 0
}

# without this var, parsing certain things can fail.
export PKGCORE_PYTHON_BINARY=/bin/false

forced_order_source="isolated-functions.lib exit-handling.lib eapi/common.lib ebuild-daemon.lib"

for x in ${forced_order_source} $(find . -name '*.lib' | sed -e 's:^\./::' | sort); do
	source "${x}"
done

# wipe our custom funcs
unset source_was_seen
unset source

echo >&2
{ echo "${pkgcore_initial_funcs}"; declare -F | cut -d ' ' -f3; } | \
sort | uniq -u | \
while read l; do
	[[ -n $l ]] && echo $l
done
