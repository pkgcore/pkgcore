#!/usr/bin/env bash
#
# Generates a list of EAPI specific functions to avoid exporting to the saved
# ebuild environment. This script is run dynamically on initialization of the
# build environment for each ebuild since different EAPIs require different
# lists of functions to be skipped.

EAPI=${1:-0}
export PKGCORE_BIN_PATH=$(dirname "$0")

# without this var, parsing certain things can fail; force to true
# so any code that tried accessing it thinks it succeeded
export PKGCORE_PYTHON_BINARY=/bin/true

source "${PKGCORE_BIN_PATH}/eapi/${EAPI}.lib" \
	|| { echo "failed loading eapi/${EAPI}.lib" >&2; exit 1; }

# grab function list *before* adding our custom declare function, otherwise
# it'll show up in the list of functions
__content=$(builtin declare -F)
declare() { echo "$2"; }
eval "${__content}" || { echo "generate EAPI func list eval failed" >&2; exit 1; }
unset -f declare
