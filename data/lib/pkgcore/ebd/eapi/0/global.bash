__phase_pkg_nofetch() {
	[[ -z ${SRC_URI} ]] && return

	echo "!!! The following are listed in SRC_URI for ${PN}:"
	local fp
	__shopt_push -f
	for fp in ${SRC_URI}; do
		echo "!!! ${fp}"
	done
	__shopt_pop
}

__phase_src_unpack() { [[ -n ${A} ]] && unpack ${A}; }

__phase_src_compile() {
	if [[ -x ./configure ]]; then
		econf
	fi
	if [[ -f Makefile || -f GNUmakefile || -f makefile ]]; then
		emake || die "emake failed"
	fi
}

__phase_src_test() {
	addpredict /
	local extra_args=( ${EXTRA_EMAKE} -j1 )
	if make check -n &> /dev/null; then
		echo ">>> Test phase [check]: ${CATEGORY}/${PF}"
		emake "${extra_args[@]}" check || die "make check failed, see above for details"
	elif make test -n &> /dev/null; then
		emake "${extra_args[@]}" test || die "make test failed, see above for details"
	else
		echo ">>> Test phase [none]: ${CATEGORY}/${PF}"
	fi
	SANDBOX_PREDICT=${SANDBOX_PREDICT%:/}
}

:
