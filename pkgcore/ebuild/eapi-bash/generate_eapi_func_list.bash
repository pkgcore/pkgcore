#!/bin/bash

EAPI=$1
export PKGCORE_BIN_PATH=$(dirname "$0")

# without this var, parsing certain things can fail; force to true
# so any code that tried accessing it thinks it succeeded
export PKGCORE_PYTHON_BINARY=/bin/true

# workaround to add required function from isolated-functions.lib without
# having to source it
__is_function() {
	declare -F "$1" &> /dev/null
} &> /dev/null

# pull in common.lib for various functions used in EAPI libs, currently
# __inject_common_phase_funcs and __inject_phase_funcs in particular
source "${PKGCORE_BIN_PATH}/eapi/common.lib" \
	|| { echo "failed loading eapi/common.lib" >&2; exit 1; }

# grab function list from common.lib, we'll need to unset them further on
__content=$(builtin declare -F)
declare() { echo "$2"; }
__common_funcs=$(eval "${__content}")
unset -f declare

source "${PKGCORE_BIN_PATH}/eapi/${EAPI}.lib" \
	|| { echo "failed loading eapi/${EAPI}.lib" >&2; exit 1; }

# remove functions pulled in by common.lib, we're only interested in the ones
# set specifically in the EAPI libs
unset -f __is_function ${__common_funcs}

# grab function list *before* adding our custom declare function, otherwise
# it'll show up in the list of functions
__content=$(builtin declare -F)
declare() { echo "$2"; }
eval "${__content}" || { echo "generate EAPI func list eval failed" >&2; exit 1; }
unset -f declare
