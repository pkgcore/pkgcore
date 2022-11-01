# Common library of shell functions for parsing various Gentoo-related data
# and leveraging pkgcore functionality.

# get an attribute for a given package
_pkgattr() {
	local prog=$(_get_caller)
	local pkg_attr=$1 pkg_atom=$2 repo=$3
	local ret=0 pid fdout fderr
	local -a pkg error

	if [[ -z ${pkg_atom} ]]; then
		echo "${prog}: enter a valid package name or repo path" >&2
		return 1
	fi

	# setup pipes for stdout/stderr capture
	local tmpdir=$(mktemp -d)
	trap "rm -rf '${tmpdir}'" EXIT HUP INT TERM
	mkfifo "${tmpdir}"/{stdout,stderr}

	if [[ -n ${repo} ]]; then
		pquery -r "${repo}" --raw --unfiltered --cpv -R --one-attr "${pkg_attr}" \
			-n -- "${pkg_atom}" >"${tmpdir}"/stdout 2>"${tmpdir}"/stderr &
	else
		pquery --ebuild-repos --raw --unfiltered --cpv -R --one-attr "${pkg_attr}" \
			-n -- "${pkg_atom}" >"${tmpdir}"/stdout 2>"${tmpdir}"/stderr &
	fi

	# capture pquery stdout/stderr into separate vars
	pid=$!
	exec {fdout}<"${tmpdir}"/stdout {fderr}<"${tmpdir}"/stderr
	rm -rf "${tmpdir}"
	mapfile -t -u ${fdout} pkg
	mapfile -t -u ${fderr} error
	wait ${pid}
	ret=$?
	exec {fdout}<&- {fderr}<&-

	if [[ ${ret} != 0 ]]; then
		# re-prefix the main pquery error message with the shell function name
		echo "${prog}: ${error[0]#pquery: error: }" >&2
		# output the remaining portion of the error message
		local line
		for line in "${error[@]:1}"; do
			echo -E "${line}" >&2
		done
		return 1
	fi

	local choice
	if [[ -z ${pkg[@]} ]]; then
		echo "${prog}: no matches found: ${pkg_atom}" >&2
		return 1
	elif [[ ${#pkg[@]} > 1 ]]; then
		echo "${prog}: multiple matches found: ${pkg_atom}" >&2
		choice=$(_choose "${pkg[@]%%|*}")
		[[ $? -ne 0 ]] && return 1
	else
		choice=-1
	fi
	echo ${pkg[${choice}]#*|}
}

# get the caller of the current function
_get_caller() {
	local caller
	if [[ ${FUNCNAME[-1]} == "source" ]]; then
		caller=$(basename ${BASH_SOURCE[-1]})
	else
		caller=${FUNCNAME[-1]}
	fi
	echo ${caller}
}

# cross-shell compatible PATH searching
_which() {
	type -P "$1" >/dev/null
}

# cross-shell compatible read num chars
_read_nchars() {
	local var
	read -n $1 var
	echo ${var}
}

# cross-shell compatible array index helper
# bash arrays start at 0
_array_index() {
	echo $1
}
