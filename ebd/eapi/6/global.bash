# Copyright: 2014-2016 Tim Harder <radhermit@gmail.com>
# license GPL2/BSD 3

__phase_src_prepare() {
	local patches
	if patches=$(declare -p PATCHES 2> /dev/null); then
		if [[ ${patches} == "declare -a "* ]]; then
			[[ ${#PATCHES[@]} -gt 0 ]] && eapply "${PATCHES[@]}"
		else
			[[ -n ${PATCHES} ]] && eapply ${PATCHES}
		fi
	fi

	eapply_user
}

__phase_src_install() {
	if [[ -f Makefile || -f GNUmakefile || -f makefile ]]; then
		emake DESTDIR="${D}" install
	fi

	einstalldocs
}

:
