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
