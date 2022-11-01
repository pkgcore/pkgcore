# Various internal functions

# Internal logging function, don't use this in ebuilds.
__elog_base() {
	local messagetype
	[[ -z $1 || -z ${T} || ! -d ${T}/logging ]] && return 1
	case $1 in
		INFO|WARN|ERROR|LOG|QA)
			messagetype=$1
			shift
			;;
		*)
			echo -e " ${PKGCORE_RC_BAD}*${PKGCORE_RC_NORMAL} Invalid use of internal function __elog_base(), next message will not be logged" >&2
			return 1
			;;
	esac
	echo "$*" >> "${T}/logging/${EBUILD_PHASE}.${messagetype}"
	return 0
}

__colored_output_disable() {
	PKGCORE_RC_COLS="25 80"
	PKGCORE_RC_ENDCOL=
	PKGCORE_RC_GOOD=
	PKGCORE_RC_WARN=
	PKGCORE_RC_BAD=
	PKGCORE_RC_NORMAL=
	PKGCORE_RC_HILITE=
	PKGCORE_RC_BRACKET=
} &> /dev/null

__colored_output_enable() {
	# try setting the column width to bash's internal COLUMNS variable,
	# then try to get it via stty.  no go? hardcode it to 80.
	PKGCORE_RC_COLS=${COLUMNS:-0}
	if (( PKGCORE_RC_COLS <= 0 )); then
		PKGCORE_RC_COLS=$(set -- $(stty size 2>/dev/null) ; echo ${2:-0})
		if (( PKGCORE_RC_COLS <= 0 )); then
			PKGCORE_RC_COLS=80
		fi
	fi
	export COLUMNS=${PKGCORE_RC_COLS}

	# Use PKGCORE_RC_PREFIX in build env to avoid clipping when capturing the
	# output and displaying with a custom prefix.
	PKGCORE_RC_COLS=$(( PKGCORE_RC_COLS - 8 - PKGCORE_RC_PREFIX )) # width of [ ok ] == 7

	# Now, ${PKGCORE_RC_ENDCOL} will move us to the end of the column;
	# irregardless of character width.
	export PKGCORE_RC_ENDCOL=$'\e[A\e['${PKGCORE_RC_COLS}'C'

	export PKGCORE_RC_GOOD=$'\e[32;01m'
	export PKGCORE_RC_WARN=$'\e[33;01m'
	export PKGCORE_RC_BAD=$'\e[31;01m'
	export PKGCORE_RC_HILITE=$'\e[36;01m'
	export PKGCORE_RC_BRACKET=$'\e[34;01m'
	export PKGCORE_RC_NORMAL=$'\e[0m'
} &> /dev/null

# Version of has, only to be used when the invoker knows that the targets will
# never have \001 in them.
__safe_has() {
	local needle=$1
	shift
	local IFS=$'\001'
	[[ "${IFS}${*}${IFS}" == *"${IFS}${needle}${IFS}"* ]]
}

__feature_is_enabled() {
	local IFS=$' \t\n'
	__safe_has "$1" ${FEATURES}
} &> /dev/null

__which() {
	[[ $# -ne 1 ]] && die "${FUNCNAME}: requires a single command name arg, got $@"
	type -P "$1" || die "'$1' not found in PATH"
}

__is_function() {
	declare -F "$1" &> /dev/null
} &> /dev/null

__run_function_if_exists() {
	__is_function "$1" || return 0
	"$@"
}

__qa_run_function_if_exists() {
	__is_function "$1" || return 0
	__qa_invoke "$@"
}

# Check if a directory is empty.
# Returns: 0 if empty, 1 otherwise.
__directory_is_empty() {
	__shopt_push -s dotglob nullglob
	local files=( ${1}/* )
	__shopt_pop
	[[ ${#files[@]} -gt 0 ]] && return 1
	return 0
}

# Reverse a given array.
# Example:
#	$ a=(1 2 3 4 5)
#	$ a=( $(__reverse_array a) )
#	$ echo ${a[@]}
#	5 4 3 2 1
__reverse_array() {
	local _array_ref="$1"[@]
	local -a array=( "${!_array_ref}" )
	local i
	for (( i=${#array[@]}-1 ; i>=0 ; i-- )) ; do
		echo "${array[i]}"
	done
}

__strip_duplicate_slashes() {
	if [[ -n $1 ]]; then
		local removed=$1
		while [[ ${removed} == *//* ]]; do
			removed=${removed//\/\///}
		done
		echo "${removed}"
	fi
}

declare -a PKGCORE_SHOPT_STACK

# Save the current shell option state and set a shell option.
# Returns: 0 on success, dies on failure.
__shopt_push() {
	PKGCORE_SHOPT_STACK[${#PKGCORE_SHOPT_STACK[@]}]=${BASHOPTS}
	PKGCORE_SHOPT_STACK[${#PKGCORE_SHOPT_STACK[@]}]=$-
	if [[ $1 == -[su] ]]; then
		# shopt modification
		shopt "$@" || die "bad shopt options: $@"
	elif [[ -n $@ ]]; then
		set "$@" || die "bad set invocation: $@"
	fi
	return 0
} &> /dev/null

# Revert to the most recent shell option state.
# Returns: 0 on success, dies on failure.
__shopt_pop() {
	[[ $# -ne 0 ]] && die "${FUNCNAME}: accepts no args, got $@"
	local count=$(( ${#PKGCORE_SHOPT_STACK[@]} - 1 ))
	[[ ${count} -le 0 ]] && die "${FUNCNAME}: invoked with nothing on the stack"

	local set_val=${PKGCORE_SHOPT_STACK[${count}]}
	if [[ $- != ${set_val} ]]; then
		set ${-:++${-}} ${set_val:+-${set_val}} || die "failed enforcing set state of ${set_val}"
	fi
	unset -v PKGCORE_SHOPT_STACK\[${count}\] || die "${FUNCNAME}: readonly shopt stack"

	count=$(( count - 1 ))

	local previous=${PKGCORE_SHOPT_STACK[${count}]}
	unset -v PKGCORE_SHOPT_STACK\[${count}\] || die "${FUNCNAME}: readonly shopt stack"
	[[ ${BASHOPTS} == ${previous} ]] && return 0

	local IFS=' '
	local current=${BASHOPTS}
	if [[ -n ${current} ]]; then
		shopt -u ${current//:/ } >&2 || die "failed wiping current shopt settings of ${current}"
	fi
	if [[ -n ${previous} ]]; then
		shopt -s ${previous//:/ } >&2 || die "failed forcing old shopt settings to ${previous}"
	fi
	return 0
} &> /dev/null

declare -a PKGCORE_SAVED_IFS

# Save the current IFS value and set a new one.
# Returns: 0 on success, dies on failure.
__IFS_push() {
	PKGCORE_SAVED_IFS[${#PKGCORE_SAVED_IFS[@]}]=${IFS-unset}
	if [[ $1 == unset ]]; then
		unset -v IFS || die "${FUNCNAME}: IFS is readonly"
	else
		IFS=$1
	fi
	:
}

# Revert to the most recent IFS setting.
# Returns: 0 on success, dies on failure.
__IFS_pop() {
	if [[ ${#PKGCORE_SAVED_IFS[@]} -eq 0 ]]; then
		die "${FUNCNAME}: invoked with nothing on the stack"
	fi
	IFS=${PKGCORE_SAVED_IFS[$(( ${#PKGCORE_SAVED_IFS[@]} - 1 ))]}
	if [[ ${IFS} == unset ]]; then
		unset -v IFS || die "${FUNCNAME}: IFS is readonly"
	fi
	unset -v PKGCORE_SAVED_IFS\[$(( ${#PKGCORE_SAVED_IFS[@]} - 1 ))\] || die "${FUNCNAME}: readonly IFS stack"
	:
}

declare -a PKGCORE_VAR_STACK

# Save the given variable's value and set a new one.
# Returns: 0 on success, dies on failure.
__var_push() {
	local export_opts
	if [[ $1 == -n ]]; then
		export_opts="-n"
		shift
	fi
	[[ $# -eq 0 ]] && die "${FUNCNAME}: invoked with no arguments"

	local arg var orig_val
	for arg in "$@"; do
		var=${arg%%=*}

		# If the specified variable currently has a value we save it;
		# otherwise, just push the variable name onto the stack.
		if orig_val=$(declare -p ${var} 2>/dev/null); then
			orig_val=${orig_val/declare *${var}=[\'\"]/${var}=}
			orig_val=${orig_val%[\'\"]}
		else
			orig_val=${var}
		fi

		# toss the current value
		unset -v ${var} 2>/dev/null || die "${FUNCNAME}: '${var}' is readonly"

		# export a new value if one was specified
		if [[ ${arg} == *=* ]]; then
			export ${export_opts} "${arg}" || die "${FUNCNAME}: failed to export '${arg}'"
		fi

		PKGCORE_VAR_STACK[${#PKGCORE_VAR_STACK[@]}]=${orig_val}
	done
}

# Revert the most recent variable value change.
# Returns: 0 on success, dies on failure.
__var_pop() {
	[[ ${#PKGCORE_VAR_STACK[@]} -gt 0 ]] \
		|| die "${FUNCNAME}: invoked with nothing on the stack"

	local count=$1
	case $# in
		0) count=1;;
		1) [[ ${count} == *[!0-9]* ]] && die "${FUNCNAME}: arg must be a number: $*";;
		*) die "${FUNCNAME}: only accepts one arg: $*";;
	esac

	local var arg
	while (( count-- )); do
		arg=${PKGCORE_VAR_STACK[$(( ${#PKGCORE_VAR_STACK[@]} - 1 ))]}
		var=${arg%%=*}

		# unset the variable on the top of the stack
		unset -v ${var} 2>/dev/null || die "${FUNCNAME}: '${var}' is readonly"

		# reset its value if one was stored
		if [[ ${arg} == *=* ]]; then
			export "${arg}" || die "${FUNCNAME}: failed to export '${arg}'"
		fi

		unset -v PKGCORE_VAR_STACK\[$(( ${#PKGCORE_VAR_STACK[@]} - 1 ))\] || die "${FUNCNAME}: readonly variable stack"
	done
}

declare -a PKGCORE_RESET_STACK

# Save the current shell option and variable stack states.
# Returns: 0
__env_push() {
	PKGCORE_RESET_STACK[${#PKGCORE_RESET_STACK[@]}]=${#PKGCORE_SHOPT_STACK[@]}
	PKGCORE_RESET_STACK[${#PKGCORE_RESET_STACK[@]}]=${#PKGCORE_VAR_STACK[@]}
}

# Revert to the last marked shell option and variable stack states.
# Returns: 0 on success, dies on failure.
__env_pop() {
	if [[ ${#PKGCORE_RESET_STACK[@]} -lt 2 ]]; then
		die "${FUNCNAME}: not enough values on the stack"
	fi

	local var_stack_reset=${PKGCORE_RESET_STACK[$(( ${#PKGCORE_RESET_STACK[@]} - 1 ))]}
	unset -v PKGCORE_RESET_STACK\[$(( ${#PKGCORE_RESET_STACK[@]} - 1 ))\] || die "${FUNCNAME}: readonly env stack"
	local shopt_stack_reset=${PKGCORE_RESET_STACK[$(( ${#PKGCORE_RESET_STACK[@]} - 1 ))]}
	unset -v PKGCORE_RESET_STACK\[$(( ${#PKGCORE_RESET_STACK[@]} - 1 ))\] || die "${FUNCNAME}: readonly env stack"

	while [[ ${#PKGCORE_VAR_STACK[@]} -gt ${var_stack_reset} ]]; do
		__var_pop
	done
	while [[ ${#PKGCORE_SHOPT_STACK[@]} -gt ${shopt_stack_reset} ]]; do
		__shopt_pop
	done
}

declare -a PKGCORE_STDOUT
declare -a PKGCORE_STDERR

# Echo a given command to stderr if debugging is enabled then run it while
# capturing stdout/stderr to PKGCORE_STDOUT/PKGCORE_STDERR arrays.
__run() {
	[[ ${PKGCORE_DEBUG} -ge 1 ]] && echo $1 >&2
	local ret stdout stderr
	source <({ stderr=( "$({ mapfile -t stdout< <(eval $1; ret=$?; declare -p ret >&3); } 3>&2 2>&1; declare -p stdout >&2)" ); declare -p stderr; } 2>&1)
	PKGCORE_STDOUT=( "${stdout[@]}" )
	PKGCORE_STDERR=( "${stderr[@]}" )
	[[ ${PKGCORE_DEBUG} -ge 1 ]] && printf '%b\n' "${PKGCORE_STDERR[@]}" >&2
	return ${ret}
}

# Echo a given command to stderr and then run it.
__echo_and_run() {
	[[ ! ${PKGCORE_DEBUG} -ge 1 ]] && local -x PKGCORE_DEBUG=1
	__run "$1"
}

__qa_invoke() {
	if ${PKGCORE_QA_SUPPRESSED:-false}; then
		"$@"
		return $(( $? ))
	fi
	local pkgcore_should_fail=false
	# save env and shopt settings.
	# in addition, protect the stack from bad pkgcore calls, or bad consumers accessing internals
	local PKGCORE_SAVED_IFS=()
	local PKGCORE_SHOPT_STACK=()

	__IFS_push "${IFS}"
	__shopt_push

	"$@"
	local ret=$?

	if [[ ${#PKGCORE_SAVED_IFS[@]} -ne 1 ]]; then
		echo "QA warning: unbalanced __IFS_push/__IFS_pop detected.  internal error? count was ${#PKGCORE_SAVED_IFS[@]}"
		pkgcore_should_fail=true
	fi
	if [[ ${#PKGCORE_SHOPT_STACK[@]} -ne 2 ]]; then
		echo "QA warning: unbalanced __shopt_push/__shopt_pop detected. internal error? count was ${#PKGCORE_SHOPT_STACK[@]}"
		pkgcore_should_fail=true
	fi

	if [[ ${PKGCORE_SAVED_IFS[0]} != ${IFS-unset} ]]; then
		echo "QA WARNING: invocation $@ manipulated IFS to ${IFS}, but didn't restore it to its original value!"
	fi
	__IFS_pop

	# While these echo statements are ugly, written this way to ensure bash
	# does it as a single write- aka, keep it within the size of atomic writes
	# for pipes, relevant for threaded output straight to term.
	if [[ ${PKGCORE_SHOPT_STACK[0]} != ${BASHOPTS} ]]; then
		echo "QA warning: shopt modification bled out of invocation $@"$'\n'"          : was ${PKGCORE_SHOPT_STACK[0]}"$'\n'"          : now ${BASHOPTS}" >&2
	fi

	if [[ ${PKGCORE_SHOPT_STACK[1]} != $- ]]; then
		echo "QA warning: set modification bled out of invocation $@"$'\n'"          : was ${PKGCORE_SHOPT_STACK[1]}"$'\n'"          : now $-" >&2
	fi
	__shopt_pop

	${pkgcore_should_fail} && die "invocation $@ modified globals and didn't clean up"
	return $(( ret ))
}

:
