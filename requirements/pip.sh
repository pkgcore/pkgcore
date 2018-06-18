#!/usr/bin/env bash
#
# `pip install` shim that installs packages passed to it as well as trying to
# install released build/install deps and then falling back to using git.

DIR=${BASH_SOURCE[0]%/*}
PACKAGES=( "$@" )

# Try installing the latest build/runtime deps once, if they don't exist
# install directly from the git.
INSTALLED="${VIRTUAL_ENV}"/.installed_deps
if [[ ! -f ${INSTALLED} ]]; then
	touch "${INSTALLED}"

	pip install -r "${DIR}"/build.txt 2>/dev/null
	ret=$?

	if [[ ${ret} -eq 0 ]]; then
		pip install -r "${DIR}"/install.txt 2>/dev/null
		ret=$?
	fi

	if [[ ${ret} -ne 0 ]]; then
		while read -r dep; do
			# skip installing deps when installing directly from git repos
			if [[ ${dep} =~ ^https?://.* ]]; then
				pip install -I --no-deps ${dep}
			else
				pip install -I ${dep}
			fi
		done < "${DIR}"/dev.txt
		ret=$?
	fi
fi

# install packages passed to us via tox
for package in "${PACKAGES[@]}"; do
	pip install ${package}
done
