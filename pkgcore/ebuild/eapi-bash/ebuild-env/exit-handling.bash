# Copyright 2005-2010 Brian Harring <ferringb@gmail.com>: BSD/GPL2
# Copyright 2004-2005 Gentoo Foundation: GPL2

assert() {
	local _pipestatus=${PIPESTATUS[*]}
	local x
	for x in ${_pipestatus}; do
		[ "$x" != 0 ] && die "$@"
	done
}

# this exists to protect against older env dumps that had the historical
# implementation of die that was alias based.
diefunc() {
	die "$@"
}

die() {
	set +x
	# if we were signaled to die...
	if [[ -n $EBD_DISABLE_DIEFUNC ]]; then
		return
	fi
	shift 3
	local n filespacing=0 linespacing=0
	# setup spacing to make output easier to read
	for ((n = ${#FUNCNAME[@]} - 1; n >= 0; --n)); do
		sourcefile=${BASH_SOURCE[${n}]} sourcefile=${sourcefile##*/}
		lineno=${BASH_LINENO[${n}]}
		((filespacing < ${#sourcefile})) && filespacing=${#sourcefile}
		((linespacing < ${#lineno}))     && linespacing=${#lineno}
	done

	echo "!!! ERROR: $CATEGORY/$PF failed." >&2
	echo "!!! die invoked from directory $(pwd)" >&2
	dump_trace 2 ${filespacing} ${linespacing} >&2
	echo "!!!   $(printf "%${filespacing}s" "${BASH_SOURCE[1]##*/}"), line $(printf "%${linespacing}s" "${BASH_LINENO[0]}"):  Called die" >&2
	echo "!!! The die message:" >&2
	echo "!!!  ${*:-(no error message)}" >&2
	echo "!!!" >&2
	echo "!!! If you need support, post the topmost build error, and the call stack if relevant." >&2
	if [[ "${EBUILD_PHASE/depend}" == "${EBUILD_PHASE}" ]] ; then
		local x
		for x in $EBUILD_DEATH_HOOKS; do
			${x} "$@" >&2 1>&2
		done
	fi
	echo >&2
	exit 1
}

# usage- first arg is the number of funcs on the stack to ignore.
# defaults to 1 (ignoring dump_trace)
# whitespacing for filenames
# whitespacing for line numbers
dump_trace() {
	local funcname="" sourcefile="" lineno="" n e s="yes"

	declare -i strip=1
	local filespacing=$2 linespacing=$3

	if [[ -n $1 ]]; then
		strip=$(( $1 ))
	fi
	echo "!!! Call stack:"
	for (( n = ${#FUNCNAME[@]} - 1, p = ${#BASH_ARGV[@]} ; n > $strip ; n-- )) ; do
		funcname=${FUNCNAME[${n} - 1]}
		sourcefile=$(basename ${BASH_SOURCE[${n}]})
		lineno=${BASH_LINENO[${n} - 1]}
		# Display function arguments
		args=
		if [[ -n "${BASH_ARGV[@]}" ]]; then
			for (( j = 0 ; j < ${BASH_ARGC[${n} - 1]} ; ++j )); do
				newarg=${BASH_ARGV[$(( p - j - 1 ))]}
				args="${args:+${args} }'${newarg}'"
			done
			(( p -= ${BASH_ARGC[${n} - 1]} ))
		fi
		echo "!!!   $(printf "%${filespacing}s" "${sourcefile}"), line $(printf "%${linespacing}s" "${lineno}"):  Called ${funcname}${args:+ ${args}}"
	done
}
