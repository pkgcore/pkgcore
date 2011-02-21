# Copyright 1999-2006 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header$

# Internal logging function, don't use this in ebuilds
elog_base() {
	local messagetype
	[ -z "${1}" -o -z "${T}" -o ! -d "${T}/logging" ] && return 1
	case "${1}" in
		INFO|WARN|ERROR|LOG)
			messagetype="${1}"
			shift
			;;
		*)
			echo -e " ${PKGCORE_RC_BAD}*${PKGCORE_RC_NORMAL} Invalid use of internal function elog_base(), next message will not be logged" >&2
			return 1
			;;
	esac
	echo "$*" >> ${T}/logging/${EBUILD_PHASE}.${messagetype}
	return 0
}

elog() {
	elog_base LOG "$*"
	echo -e " ${PKGCORE_RC_GOOD}*${PKGCORE_RC_NORMAL} $*" >&2
	return 0
}

einfo() {
	einfon "$*\n"
	PKGCORE_RC_LAST_CMD="einfo"
	return 0
}

einfon() {
	elog_base INFO "$*"
	echo -ne " ${PKGCORE_RC_GOOD}*${PKGCORE_RC_NORMAL} $*" >&2
	PKGCORE_RC_LAST_CMD="einfon"
	return 0
}

ewarn() {
	elog_base WARN "$*"
	echo -e " ${PKGCORE_RC_WARN}*${PKGCORE_RC_NORMAL} $*" >&2
	PKGCORE_RC_LAST_CMD="ewarn"
	return 0
}

eerror() {
	elog_base ERROR "$*"
	echo -e " ${PKGCORE_RC_BAD}*${PKGCORE_RC_NORMAL} $*" >&2
	PKGCORE_RC_LAST_CMD="eerror"
	return 0
}

ebegin() {
	local msg="$* ..."
	einfon "${msg}"
	echo >&2
	PKGCORE_RC_LAST_CMD="ebegin"
	return 0
}

_eend() {
	local retval=${1:-0} efunc=${2:-eerror} msg
	shift 2

	if [[ ${retval} == "0" ]] ; then
		msg="${PKGCORE_RC_BRACKET}[ ${PKGCORE_RC_GOOD}ok${PKGCORE_RC_BRACKET} ]${PKGCORE_RC_NORMAL}"
	else
		if [[ -n $* ]] ; then
			${efunc} "$*"
		fi
		msg="${PKGCORE_RC_BRACKET}[ ${PKGCORE_RC_BAD}!!${PKGCORE_RC_BRACKET} ]${PKGCORE_RC_NORMAL}"
	fi

	echo -e "${PKGCORE_RC_ENDCOL}  ${msg}" >&2

	return ${retval}
}

eend() {
	local retval=${1:-0}
	shift

	_eend ${retval} eerror "$*"

	return ${retval}
}

KV_major() {
	[[ -z $1 ]] && return 1

	local KV=$@
	echo "${KV%%.*}"
}

KV_minor() {
	[[ -z $1 ]] && return 1

	local KV=$@
	KV=${KV#*.}
	echo "${KV%%.*}"
}

KV_micro() {
	[[ -z $1 ]] && return 1

	local KV=$@
	KV=${KV#*.*.}
	echo "${KV%%[^[:digit:]]*}"
}

KV_to_int() {
	[[ -z $1 ]] && return 1

	local KV_MAJOR=$(KV_major "$1")
	local KV_MINOR=$(KV_minor "$1")
	local KV_MICRO=$(KV_micro "$1")
	local KV_int=$(( KV_MAJOR * 65536 + KV_MINOR * 256 + KV_MICRO ))

	# We make version 2.2.0 the minimum version we will handle as
	# a sanity check ... if its less, we fail ...
	if [[ ${KV_int} -ge 131584 ]] ; then
		echo "${KV_int}"
		return 0
	fi

	return 1
}

get_KV() {
	echo $(KV_to_int "$(uname -r)")
}

unset_colors() {
	PKGCORE_RC_COLS="25 80"
	PKGCORE_RC_ENDCOL=
	PKGCORE_RC_GOOD=
	PKGCORE_RC_WARN=
	PKGCORE_RC_BAD=
	PKGCORE_RC_NORMAL=
	PKGCORE_RC_HILITE=
	PKGCORE_RC_BRACKET=
}

set_colors() {
	# try setting the column width to bash's internal COLUMNS variable,
	# then try to get it via stty.  no go? hardcode it to 80.
	PKGCORE_RC_COLS=${COLUMNS:-0}
	(( PKGCORE_RC_COLS == 0 )) && PKGCORE_RC_COLS=$(set -- `stty size 2>/dev/null` ; echo $2)
	(( PKGCORE_RC_COLS > 0 )) || (( PKGCORE_RC_COLS = 80 ))
	PKGCORE_RC_COLS=$((${PKGCORE_RC_COLS} - 8))	# width of [ ok ] == 7

	PKGCORE_RC_ENDCOL=$'\e[A\e['${PKGCORE_RC_COLS}'C'
	# Now, ${PKGCORE_RC_ENDCOL} will move us to the end of the
	# column;  irregardless of character width

	PKGCORE_RC_GOOD=$'\e[32;01m'
	PKGCORE_RC_WARN=$'\e[33;01m'
	PKGCORE_RC_BAD=$'\e[31;01m'
	PKGCORE_RC_HILITE=$'\e[36;01m'
	PKGCORE_RC_BRACKET=$'\e[34;01m'
	PKGCORE_RC_NORMAL=$'\e[0m'
}

has() {
	local x

	local me=$1
	shift

	for x in "$@"; do
		if [[ ${x} == ${me} ]]; then
			return 0
		fi
	done
	return 1
}

is_function() {
	[[ $(type -t "$1") == function ]]
}

run_function_if_exists() {
	is_function "$1" && "$@"
}


unset_colors
DONT_EXPORT_VARS="${DONT_EXPORT_VARS} PKGCORE_RC_.*"
DONT_EXPORT_FUNCS="${DONT_EXPORT_FUNCS} run_function_if_exists is_function"
true
