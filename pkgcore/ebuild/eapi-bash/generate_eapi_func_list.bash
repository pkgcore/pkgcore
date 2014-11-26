#!/bin/bash

EAPI=$1
export PKGCORE_BIN_PATH=$(dirname "$0")

# without this var, parsing certain things can fail; force to true
# so any code that tried accessing it thinks it succeeded
export PKGCORE_PYTHON_BINARY=/bin/true

source "${PKGCORE_BIN_PATH}/eapi/${EAPI}.lib" \
	|| { echo "failed loading eapi/${EAPI}.lib" >&2; exit 1; }

# Grab the vars /before/ adding our custom declare function, else it'll
# show up in the list of functions.
__content=$(builtin declare -F)
declare() {
	echo "$2"
}
eval "${__content}" || { echo "generate EAPI func list eval failed" >&2; exit 1; }
unset declare
