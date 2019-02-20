# Copyright: 2014-2016 Tim Harder <radhermit@gmail.com>
# license GPL2/BSD 3

PKGCORE_EAPPLY_USER=false

__phase_post_src_prepare() {
	${PKGCORE_EAPPLY_USER} || die "eapply_user (or default) must be called in src_prepare()"
}

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
