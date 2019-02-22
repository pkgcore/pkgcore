# Copyright 2005-2012 Brian Harring <ferringb@gmail.com>: BSD/GPL2
# Copyright 2004-2005 Gentoo Foundation: GPL2

# Check whether any command in the most recently executed foreground pipe
# returned non-zero and if so calls die passing along any given parameters.
assert() {
	local pipestatus=${PIPESTATUS[*]}
	[[ -z ${pipestatus//[ 0]/} ]] || die "$@ (pipestatus: ${pipestatus})"
}

# Abort the current build process (see PMS for details).
die() {
	set +x
	# if we were signaled to die...
	if [[ -n ${EBD_DISABLE_DIEFUNC} ]]; then
		return
	fi

	if [[ ${PKGCORE_NONFATAL_DIE} && $1 == "-n" ]]; then
		shift
		if ${PKGCORE_NONFATAL}; then
			[[ $# -gt 0 ]] && eerror "$*"
			return 1
		fi
	fi

	# If stderr is redirected, store the error message in a temp file to be
	# sent back to python for output.
	local stderr
	if [[ ! -t 2 ]]; then
		if [[ -n ${T} ]]; then
			stderr=$(mktemp -p "${T}" ".die_XXXXXX")
			exec 2>"${stderr}"
		else
			stderr="$@"
		fi
	fi

	local n filespacing=0 linespacing=0 sourcefile lineno
	# setup spacing to make output easier to read
	for (( n = ${#FUNCNAME[@]} - 1 ; n >= 0 ; --n )); do
		sourcefile=${BASH_SOURCE[${n}]} sourcefile=${sourcefile##*/}
		lineno=${BASH_LINENO[${n}]}
		(( filespacing < ${#sourcefile} )) && filespacing=${#sourcefile}
		(( linespacing < ${#lineno} ))     && linespacing=${#lineno}
	done

	local phase_str=
	[[ -n ${EBUILD_PHASE} ]] && phase_str=" (${EBUILD_PHASE} phase)"
	eerror "ERROR: ${CATEGORY}/${PF}::${PKGCORE_PKG_REPO} failed${phase_str}:"

	# split error message by newline so every line gets prefixed properly
	local line
	echo -e "${@:-(no error message)}" | while IFS= read -r line; do
		eerror "  ${line}"
	done

	if [[ -n ${PKGCORE_IS_NOT_HELPER} ]]; then
		eerror
		__dump_trace 2 ${filespacing} ${linespacing} >&2
		eerror "   $(printf "%${filespacing}s" "${BASH_SOURCE[1]##*/}"), line $(printf "%${linespacing}s" "${BASH_LINENO[0]}"):  called die"
	fi
	if ${PKGCORE_DIE_OUTPUT_DETAILS-true}; then
		if [[ -n ${PKGCORE_IS_NOT_HELPER} ]]; then
			eerror
			eerror "If you need support, post the topmost build error, and the call stack if relevant."
		fi
		local hook
		for hook in ${EBUILD_DEATH_HOOKS}; do
			${hook} >&2 1>&2
		done
	fi

	local working_dir=$(pwd)
	if [[ ${PKGCORE_EBD_PATH} != ${working_dir} ]]; then
		eerror
		eerror "Working directory: '${working_dir}'"
	fi

	if [[ ${BASHPID} != ${PKGCORE_EBUILD_PROCESS_PID} ]]; then
		if [[ -n ${PKGCORE_EBUILD_PROCESS_PID} ]]; then
			local -a error_msg
			# format error message for transmission
			if [[ -n ${stderr} ]]; then
				if [[ -f ${stderr} ]]; then
					mapfile -t error_msg <${stderr}
					rm -f "${stderr}"
				else
					error_msg+=( ${stderr} )
				fi
			fi

			# Tell the python side we're dying so it should handle cleanup,
			# this forces die() to work in subshell environments.
			__ebd_write_line "term"
			# Send any error message back to python if unable to output it here
			# due to redirection.
			printf "%s\0" "${error_msg[@]}" >&${PKGCORE_EBD_WRITE_FD}
			__ebd_write_line
		fi
	fi

	exit 1
}

# usage- first arg is the number of funcs on the stack to ignore.
# defaults to 1 (ignoring __dump_trace)
# whitespacing for filenames
# whitespacing for line numbers
__dump_trace() {
	declare -i strip=${1:-1}
	local filespacing=$2 linespacing=$3
	local n p

	(( n = ${#FUNCNAME[@]} - 1 ))
	(( p = ${#BASH_ARGV[@]} ))
	# Drop internals up to the __qa_invoke() call when debugging isn't enabled.
	if [[ -z ${PKGCORE_DEBUG} ]]; then
		while (( n > 0 )); do
			[[ ${FUNCNAME[${n}]} == __qa_invoke ]] && break
			(( p -= ${BASH_ARGC[${n} - 1]} ))
			(( n-- ))
		done
		if (( n == 0 )); then
			(( n = ${#FUNCNAME[@]} - 1 ))
			(( p = ${#BASH_ARGV[@]} ))
		fi
	fi

	eerror "Call stack:"
	local funcname= sourcefile= lineno=
	for (( n; n > ${strip}; n-- )); do
		funcname=${FUNCNAME[${n} - 1]}
		sourcefile=${BASH_SOURCE[${n}]##*/}
		lineno=${BASH_LINENO[${n} - 1]}
		# Display function arguments
		local args= newargs=
		local j
		if [[ ${#BASH_ARGV[@]} -gt 0 ]]; then
			for (( j = 0 ; j < ${BASH_ARGC[${n} - 1]} ; ++j )); do
				newargs=${BASH_ARGV[$(( p - j - 1 ))]}
				args="${args:+${args} }'${newargs}'"
			done
			(( p -= ${BASH_ARGC[${n} - 1]} ))
		fi
		eerror "   $(printf "%${filespacing}s" "${sourcefile}"), line $(printf "%${linespacing}s" "${lineno}"):  called ${funcname}${args:+ ${args}}"
	done
}

:
