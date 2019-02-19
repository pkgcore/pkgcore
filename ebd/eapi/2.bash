# Copyright: 2011-2012 Brian Harring <ferringb@gmail.com>
# license GPL2/BSD 3

source "${PKGCORE_EBD_PATH}"/eapi/1.bash

__phase_src_prepare() { :; }

__phase_src_configure() {
	if [[ -x ${ECONF_SOURCE:-.}/configure ]]; then
		econf
	fi
}

__phase_src_compile() {
	if [[ -f Makefile || -f GNUmakefile || -f makefile ]]; then
		emake || die "emake failed"
	fi
}

:
