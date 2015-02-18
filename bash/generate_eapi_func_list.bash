#!/bin/bash
#
# Generates a list of EAPI specific functions to avoid exporting to the saved
# ebuild environment. This script is run dynamically on initialization of the
# build environment for each ebuild since different EAPIs require different
# lists of functions to be skipped.

EAPI=$1
export PKGCORE_BIN_PATH=$(dirname "$0")

# without this var, parsing certain things can fail; force to true
# so any code that tried accessing it thinks it succeeded
export PKGCORE_PYTHON_BINARY=/bin/true

# sourcing EAPI specific libs requires a couple functions from
# isolated-functions.lib, specifically __safe_has() and __is_function() are
# used in __inject_phase_funcs() from common.lib
source "${PKGCORE_BIN_PATH}/isolated-functions.lib" \
	|| { echo "failed loading isolated-functions.lib" >&2; exit 1; }

# pull in common.lib for various functions used in EAPI libs, currently
# __inject_common_phase_funcs() and __inject_phase_funcs() in particular
source "${PKGCORE_BIN_PATH}/eapi/common.lib" \
	|| { echo "failed loading eapi/common.lib" >&2; exit 1; }

# grab current function list, we'll need to unset them further on
__content=$(builtin declare -F)
declare() { echo "$2"; }
__common_funcs=$(eval "${__content}")
unset -f declare

source "${PKGCORE_BIN_PATH}/eapi/${EAPI}.lib" \
	|| { echo "failed loading eapi/${EAPI}.lib" >&2; exit 1; }

# remove functions pulled in by EAPI lib deps, we're only interested in the
# ones set specifically in the EAPI libs
unset -f ${__common_funcs}

# grab function list *before* adding our custom declare function, otherwise
# it'll show up in the list of functions
__content=$(builtin declare -F)
declare() { echo "$2"; }
eval "${__content}" || { echo "generate EAPI func list eval failed" >&2; exit 1; }
unset -f declare
