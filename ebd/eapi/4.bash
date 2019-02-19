# Copyright: 2011-2012 Brian Harring <ferringb@gmail.com>
# license GPL2/BSD 3

source "${PKGCORE_EBD_PATH}"/eapi/3.bash

__econf_options_eapi4() {
	if [[ $1 == *"--disable-dependency-tracking"* ]]; then
		echo --disable-dependency-tracking
	fi
}

nonfatal() {
	PKGCORE_NONFATAL=true "$@"
}

__phase_funcs_src_install_eapi4() {
	docompress() {
		if [[ $1 == "-x" ]]; then
			shift
			PKGCORE_DOCOMPRESS_SKIP+=( "$@" )
		else
			PKGCORE_DOCOMPRESS+=( "$@" )
		fi
	}
}

__phase_src_install() {
	if [[ -f Makefile || -f GNUmakefile || -f makefile ]]; then
		emake DESTDIR="${D}" install
	fi

	local docs PKGCORE_DOCDESTTREE=
	if ! docs=$(declare -p DOCS 2> /dev/null); then
		for docs in README* ChangeLog AUTHORS NEWS TODO CHANGES \
				THANKS BUGS FAQ CREDITS CHANGELOG; do
			[[ -s ${docs} ]] && dodoc "${docs}"
		done
	elif [[ ${docs} == "declare -a "* ]]; then
		dodoc "${DOCS[@]}"
	else
		dodoc ${DOCS}
	fi
}

default_src_install() { __phase_src_install; }

:
