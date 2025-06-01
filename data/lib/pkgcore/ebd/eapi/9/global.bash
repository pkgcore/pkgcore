# (c) 2022-2025 Gentoo Authors
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

edo() {
	# list of special characters taken from sh_contains_shell_metas
	# in shquote.c (bash-5.2)
	local a out regex='[] '\''"\|&;()<>!{}*[?^$`]|^[#~]|[=:]~'

	[[ $# -ge 1 ]] || die "edo: at least one argument needed"

	for a; do
		# quote if (and only if) necessary
		[[ ${a} =~ ${regex} || ! ${a} =~ ^[[:print:]]+$ ]] && a=${a@Q}
		out+=" ${a}"
	done

	einfon
	printf '%s\n' "${out:1}" >&2
	"$@" || die -n "Failed to run command: ${1}"
}

:
