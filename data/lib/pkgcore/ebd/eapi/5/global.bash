# parallel tests are allowed (no forced -j1)
__phase_src_test() {
	addpredict /
	local extra_args=( ${EXTRA_EMAKE} )
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
