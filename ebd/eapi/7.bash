# Copyright: 2016-2018 Tim Harder <radhermit@gmail.com>
# Copyright: 2017-2018 Michał Górny <mgorny@gentoo.org>
# Copyright: 2017-2018 Ulrich Müller <ulm@gentoo.org>
# license GPL2/BSD 3

source "${PKGCORE_EBD_PATH}"/eapi/6.bash

PKGCORE_BANNED_FUNCS+=( libopts )

__econf_options_eapi7() {
	if [[ $1 == *"--with-sysroot"* ]]; then
		echo --with-sysroot="${ESYSROOT:-/}"
	fi
}

dostrip() {
	if [[ $1 == "-x" ]]; then
		shift
		PKGCORE_DOSTRIP_SKIP+=( "$@" )
	else
		PKGCORE_DOSTRIP+=( "$@" )
	fi
}

__query_version_funcs() {
	local atom root

	# default to root settings for -r option
	if ${PKGCORE_PREFIX_SUPPORT}; then
		root=${EROOT}
	else
		root=${ROOT}
	fi

	case $1 in
		-r) shift ;;
		-d)
			if ${PKGCORE_PREFIX_SUPPORT}; then
				root=${ESYSROOT}
			else
				root=${SYSROOT}
			fi
			shift ;;
		-b)
			if ${PKGCORE_PREFIX_SUPPORT}; then
				root=/${EPREFIX}
			else
				root=/
			fi
			shift ;;
	esac

	atom=$1
	shift
	[[ $# -gt 0 ]] && die "${FUNCNAME[1]}: unknown argument(s): $*"

	PKGCORE_DISABLE_COMPAT=true __portageq "${FUNCNAME[1]}" "${atom}" --domain-at-root "${root}"
}

__ver_parse_range() {
	local range=${1}
	local max=${2}

	[[ ${range} == [0-9]* ]] || die "${FUNCNAME}: range must start with a number"
	start=${range%-*}
	[[ ${range} == *-* ]] && end=${range#*-} || end=${start}
	if [[ ${end} ]]; then
		[[ ${start} -le ${end} ]] || die "${FUNCNAME}: end of range must be >= start"
		[[ ${end} -le ${max} ]] || end=${max}
	else
		end=${max}
	fi
}

__ver_split() {
	local v=${1} LC_ALL=C

	comp=()

	# get separators and components
	local s c
	while [[ ${v} ]]; do
		# cut the separator
		s=${v%%[a-zA-Z0-9]*}
		v=${v:${#s}}
		# cut the next component; it can be either digits or letters
		[[ ${v} == [0-9]* ]] && c=${v%%[^0-9]*} || c=${v%%[^a-zA-Z]*}
		v=${v:${#c}}

		comp+=( "${s}" "${c}" )
	done
}

ver_cut() {
	local range=${1}
	local v=${2:-${PVR}}
	local start end
	local -a comp

	__ver_split "${v}"
	local max=$((${#comp[@]}/2))
	__ver_parse_range "${range}" "${max}"

	local IFS=
	if [[ ${start} -gt 0 ]]; then
		start=$(( start*2 - 1 ))
	fi
	echo "${comp[*]:start:end*2-start}"
}

ver_rs() {
	local v
	(( ${#} & 1 )) && v=${@: -1} || v=${PVR}
	local start end i
	local -a comp

	__ver_split "${v}"
	local max=$((${#comp[@]}/2 - 1))

	while [[ ${#} -ge 2 ]]; do
		__ver_parse_range "${1}" "${max}"
		for (( i = start*2; i <= end*2; i+=2 )); do
			[[ ${i} -eq 0 && -z ${comp[i]} ]] && continue
			comp[i]=${2}
		done
		shift 2
	done

	local IFS=
	echo "${comp[*]}"
}

__ver_compare_int() {
	local a=$1 b=$2 d=$(( ${#1}-${#2} ))

	# Zero-pad to equal length if necessary.
	if [[ ${d} -gt 0 ]]; then
		printf -v b "%0${d}d%s" 0 "${b}"
	elif [[ ${d} -lt 0 ]]; then
		printf -v a "%0$(( -d ))d%s" 0 "${a}"
	fi

	[[ ${a} > ${b} ]] && return 3
	[[ ${a} == "${b}" ]]
}

__ver_compare() {
	local va=${1} vb=${2} a an al as ar b bn bl bs br re LC_ALL=C

	re="^([0-9]+(\.[0-9]+)*)([a-z]?)((_(alpha|beta|pre|rc|p)[0-9]*)*)(-r[0-9]+)?$"

	[[ ${va} =~ ${re} ]] || die "${FUNCNAME}: invalid version: ${va}"
	an=${BASH_REMATCH[1]}
	al=${BASH_REMATCH[3]}
	as=${BASH_REMATCH[4]}
	ar=${BASH_REMATCH[7]}

	[[ ${vb} =~ ${re} ]] || die "${FUNCNAME}: invalid version: ${vb}"
	bn=${BASH_REMATCH[1]}
	bl=${BASH_REMATCH[3]}
	bs=${BASH_REMATCH[4]}
	br=${BASH_REMATCH[7]}

	# Compare numeric components (PMS algorithm 3.2)
	# First component
	__ver_compare_int "${an%%.*}" "${bn%%.*}" || return

	while [[ ${an} == *.* && ${bn} == *.* ]]; do
		# Other components (PMS algorithm 3.3)
		an=${an#*.}
		bn=${bn#*.}
		a=${an%%.*}
		b=${bn%%.*}
		if [[ ${a} == 0* || ${b} == 0* ]]; then
			# Remove any trailing zeros
			[[ ${a} =~ 0+$ ]] && a=${a%"${BASH_REMATCH[0]}"}
			[[ ${b} =~ 0+$ ]] && b=${b%"${BASH_REMATCH[0]}"}
			[[ ${a} > ${b} ]] && return 3
			[[ ${a} < ${b} ]] && return 1
		else
			__ver_compare_int "${a}" "${b}" || return
		fi
	done
	[[ ${an} == *.* ]] && return 3
	[[ ${bn} == *.* ]] && return 1

	# Compare letter components (PMS algorithm 3.4)
	[[ ${al} > ${bl} ]] && return 3
	[[ ${al} < ${bl} ]] && return 1

	# Compare suffixes (PMS algorithm 3.5)
	as=${as#_}${as:+_}
	bs=${bs#_}${bs:+_}
	while [[ -n ${as} && -n ${bs} ]]; do
		# Compare each suffix (PMS algorithm 3.6)
		a=${as%%_*}
		b=${bs%%_*}
		if [[ ${a%%[0-9]*} == "${b%%[0-9]*}" ]]; then
			__ver_compare_int "${a##*[a-z]}" "${b##*[a-z]}" || return
		else
			# Check for p first
			[[ ${a%%[0-9]*} == p ]] && return 3
			[[ ${b%%[0-9]*} == p ]] && return 1
			# Hack: Use that alpha < beta < pre < rc alphabetically
			[[ ${a} > ${b} ]] && return 3 || return 1
		fi
		as=${as#*_}
		bs=${bs#*_}
	done
	if [[ -n ${as} ]]; then
		[[ ${as} == p[_0-9]* ]] && return 3 || return 1
	elif [[ -n ${bs} ]]; then
		[[ ${bs} == p[_0-9]* ]] && return 1 || return 3
	fi

	# Compare revision components (PMS algorithm 3.7)
	__ver_compare_int "${ar#-r}" "${br#-r}" || return

	return 2
}

ver_test() {
	local va op vb

	if [[ $# -eq 3 ]]; then
		va=${1}
		shift
	else
		va=${PVR}
	fi

	[[ $# -eq 2 ]] || die "${FUNCNAME}: bad number of arguments"

	op=${1}
	vb=${2}

	case ${op} in
		-eq|-ne|-lt|-le|-gt|-ge) ;;
		*) die "${FUNCNAME}: invalid operator: ${op}" ;;
	esac

	__ver_compare "${va}" "${vb}"
	test $? "${op}" 2
}

:
