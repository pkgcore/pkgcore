# various helper functionality

error() {
	echo "${HELPER_ERROR_PREFIX}: ${@-no message given}" >&2
	failed=true
}

warn() {
	echo "${HELPER_ERROR_PREFIX}: warning, ${@-no message given}" >&2
}

info() {
	echo "${HELPER_ERROR_PREFIX}: $@" >&2
}

check_args() {
	local tense="argument"
	local min=$(( $1 ))
	local max
	[[ ${min} -gt 1 ]] && tense="arguments"
	if [[ $2 == '-' ]]; then
		max=${HELPER_ARG_COUNT}
	elif [[ -z $2 ]]; then
		max=$1
	fi
	max=$(( max ))

	if [[ ${HELPER_ARG_COUNT} -ge ${min} && ${HELPER_ARG_COUNT} -le ${max} ]]; then
		return 0
	fi
	if [[ ${min} -eq ${max} ]]; then
		die "${HELPER_ERROR_PREFIX}: requires exactly ${min} ${tense}, got ${HELPER_ARG_COUNT}"
	elif [[ $2 == '-' ]]; then
		die "${HELPER_ERROR_PREFIX}: requires at least ${min} ${tense}, got ${HELPER_ARG_COUNT}"
	else:
		die "${HELPER_ERROR_PREFIX}: requires at least ${min} ${tense}, and at most ${max} arguments, got ${HELPER_ARG_COUNT}"
	fi
}

check_command() {
	local ret
	"$@"
	ret=$?
	[[ ${ret} == 0 ]] && return 0
	error "exitcode ${ret} from $*"
	return $(( ret ))
}

check_command_or_stop() {
	check_command "$@"
	__helper_check_exit $? "$@ failed, cannot continue"
	return 0
}

__helper_exit() {
	local ret=$1
	shift
	[[ ${ret} == 0 ]] && exit 0

	local error_msg="${HELPER_ERROR_PREFIX}: exitcode ${ret}"
	[[ -n $@ ]] && error_msg+=": $@"

	if ${PKGCORE_NONFATAL}; then
		eerror "${error_msg}"
		exit ${ret}
	fi

	die "${error_msg}"
}

__helper_failed() {
	PKGCORE_IS_NOT_HELPER=
	die "helper failed: ${BASH_COMMAND}"
}

__helper_check_exit() {
	[[ $1 == 0 ]] && return
	shift
	__helper_exit "$@"
}
