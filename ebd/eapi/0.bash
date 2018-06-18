# Copyright: 2012 Brian Harring <ferringb@gmail.com>
# license GPL2/BSD 3

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

__phase_src_unpack() {
	if [[ -n ${A} ]]; then
		unpack ${A}
	fi
}

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
		emake "${extra_args[@]}" check || die "Make check failed. See above for details."
	elif make test -n &> /dev/null; then
		emake "${extra_args[@]}" test || die "Make test failed. See above for details."
	else
		echo ">>> Test phase [none]: ${CATEGORY}/${PF}"
	fi
	SANDBOX_PREDICT=${SANDBOX_PREDICT%:/}
}
