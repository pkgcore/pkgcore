__phase_src_compile() {
	if [[ -x ${ECONF_SOURCE:-.}/configure ]]; then
		econf
	fi
	if [[ -f Makefile || -f GNUmakefile || -f makefile ]]; then
		emake || die "emake failed"
	fi
}

:
