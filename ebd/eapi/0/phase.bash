## Package manager query commands

has_version() { return $(__ebd_ipc_cmd ${FUNCNAME} "" "$@"); }
best_version() { __ebd_ipc_cmd ${FUNCNAME} "" "$@"; }

## USE flag commands

use() {
	if [[ ! ${1#!} =~ ${PKGCORE_IUSE_EFFECTIVE} ]]; then
		die "USE flag '${1#!}' not in IUSE for ${CATEGORY}/${PF}"
	fi

	# Ensure USE is split on normal IFS.
	local IFS=$' \t\n'

	if [[ ${1:0:1} == "!" ]]; then
		! __safe_has "${1#!}" ${USE}
	else
		__safe_has "$1" ${USE}
	fi
}

usev() {
	if use "$1"; then
		echo "${1#!}"
		return 0
	fi
	return 1
}

useq() {
	use "$@"
}

use_with() {
	if [[ -z $1 ]]; then
		echo "!!! use_with() called without a parameter." >&2
		echo "!!! use_with <USEFLAG> [<flagname> [value]]" >&2
		return
	fi

	local uw_suffix=""
	if __safe_has "${EAPI}" 0 1 2 3; then
		uw_suffix=${3:+=$3}
	else
		uw_suffix=${3+=$3}
	fi

	local uword=$2
	if [[ -z ${uword} ]]; then
		uword=$1
	fi

	if use "$1"; then
		echo "--with-${uword}${uw_suffix}"
		return 0
	fi
	echo "--without-${uword}"
	return 1
}

use_enable() {
	if [[ -z $1 ]]; then
		echo "!!! use_enable() called without a parameter." >&2
		echo "!!! use_enable <USEFLAG> [<flagname> [value]]" >&2
		return
	fi

	local ue_suffix=""
	if __safe_has "${EAPI}" 0 1 2 3; then
		ue_suffix=${3:+=$3}
	else
		ue_suffix=${3+=$3}
	fi

	local uword=$2
	if [[ -z ${uword} ]]; then
		uword=$1
	fi

	if use "$1"; then
		echo "--enable-${uword}${ue_suffix}"
		return 0
	fi
	echo "--disable-${uword}"
	return 1
}

## Misc commands

unpack() { __ebd_ipc_cmd ${FUNCNAME} "" "$@"; }

:
