#!/usr/bin/env bash
#
# Generates a list of EAPI specific functions to avoid exporting to the saved
# ebuild environment.
#
# This script is run dynamically in a repo or tarball layout on initialization
# of the build environment for each ebuild since different EAPIs require
# different lists of functions to be skipped. For installed versions, static
# function lists are generated at install time and used instead.

EAPI=${1:-0}
export PKGCORE_BIN_PATH=$(dirname "$0")

# without this var, parsing certain things can fail; force to true if unset or
# null so any code that tried accessing it thinks it succeeded
export PKGCORE_PYTHON_BINARY=${PKGCORE_PYTHON_BINARY:-/bin/true}

source "${PKGCORE_BIN_PATH}/eapi/${EAPI}.lib" \
	|| { echo "failed loading eapi/${EAPI}.lib" >&2; exit 1; }

result=$(compgen -A function)
# Sorting order; put PMS functionality first, then our internals.
result=$(echo "${result}" | grep -v "^__"; echo "${result}" | grep "^__")

echo "${result}"
