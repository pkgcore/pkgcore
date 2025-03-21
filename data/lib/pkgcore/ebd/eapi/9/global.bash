# (c) 2024-2025 Gentoo Authors
# SPDX-License-Identifier: GPL-2.0-or-later

pipestatus() {
	# copied from eapi9-pipestatus.eclass
	local status=( "${PIPESTATUS[@]}" )
	local s ret=0 verbose=""

	[[ ${1} == -v ]] && { verbose=1; shift; }
	[[ $# -ne 0 ]] && die "usage: ${FUNCNAME} [-v]"

	for s in "${status[@]}"; do
		[[ ${s} -ne 0 ]] && ret=${s}
	done

	[[ ${verbose} ]] && echo "${status[@]}"

	return "${ret}"
}

:
