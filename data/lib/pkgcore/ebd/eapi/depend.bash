# Common EAPI functions

has() {
	local needle=$1
	shift

	local IFS=$'\001'

	# try fast mode first; no IFS match is guaranteed that the needle isn't there.
	[[ "${IFS}${*}${IFS}" != *"${IFS}${needle}${IFS}"* ]] && return 1

	# If we have a match, ensure it's not due to $@ already having \001 in it.
	# unlikely, but better safe than sorry.
	IFS=' '
	[[ *$'\001'* != $* ]] && return 0

	# \001 for some insane reason was in $@; fallback to the slow for loop.
	# Suppress debug output for this part however.
	__shopt_push +x
	local x
	for x in "$@"; do
		if [[ ${x} == ${needle} ]]; then
			__shopt_pop
			return 0
		fi
	done
	__shopt_pop
	return 1
}

hasq() {
	has ${EBUILD_PHASE} prerm postrm || eqawarn \
		"QA Notice: The 'hasq' function is deprecated (replaced by 'has')"
	has "$@"
}

hasv() {
	has "$@" && echo "$1"
}

# stubbed debug commands to avoid debug output during metadata generation
debug-print() { :; }
debug-print-function() { :; }
debug-print-section() { :; }

# output commands
eqawarn() {
	__elog_base QA "$*"
	printf " ${PKGCORE_RC_WARN}*${PKGCORE_RC_NORMAL} %b\n" "${*}" >&2
	PKGCORE_RC_LAST_CMD="eqawarn"
	return 0
}

elog() {
	__elog_base LOG "$*"
	printf " ${PKGCORE_RC_GOOD}*${PKGCORE_RC_NORMAL} %b\n" "${*}" >&2
	PKGCORE_RC_LAST_CMD="elog"
	return 0
}

einfo() {
	printf " ${PKGCORE_RC_GOOD}*${PKGCORE_RC_NORMAL} %b\n" "${*}" >&2
	PKGCORE_RC_LAST_CMD="einfo"
	return 0
}

einfon() {
	__elog_base INFO "$*"
	printf " ${PKGCORE_RC_GOOD}*${PKGCORE_RC_NORMAL} %b" "${*}" >&2
	PKGCORE_RC_LAST_CMD="einfon"
	return 0
}

ewarn() {
	__elog_base WARN "$*"
	printf " ${PKGCORE_RC_WARN}*${PKGCORE_RC_NORMAL} %b\n" "${*}" >&2
	PKGCORE_RC_LAST_CMD="ewarn"
	return 0
}

eerror() {
	__elog_base ERROR "$*"
	printf " ${PKGCORE_RC_BAD}*${PKGCORE_RC_NORMAL} %b\n" "${*}" >&2
	PKGCORE_RC_LAST_CMD="eerror"
	return 0
}

ebegin() {
	local msg="$* ..."
	einfon "${msg}"
	echo
	PKGCORE_RC_LAST_CMD="ebegin"
	return 0
}

eend() {
	local retval=${1:-0}
	shift

	local msg

	if [[ ${retval} == 0 ]]; then
		msg="${PKGCORE_RC_BRACKET}[ ${PKGCORE_RC_GOOD}ok${PKGCORE_RC_BRACKET} ]${PKGCORE_RC_NORMAL}"
	else
		if [[ $# -ne 0 ]]; then
			eerror "$*"
		fi
		msg="${PKGCORE_RC_BRACKET}[ ${PKGCORE_RC_BAD}!!${PKGCORE_RC_BRACKET} ]${PKGCORE_RC_NORMAL}"
	fi

	echo -e "${PKGCORE_RC_ENDCOL} ${msg}" >&2

	return ${retval}
}

:
