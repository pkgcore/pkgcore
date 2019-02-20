eapply() {
	local -a options files
	local token end_options bad_options

	for token in "${@}"; do
		if [[ -n ${end_options} ]]; then
			files+=( "${token}" )
		elif [[ ${token} == -- ]]; then
			[[ ${#files[@]} -eq 0 ]] || bad_options=1
			end_options=1
		elif [[ ${token} == -* ]]; then
			[[ ${#files[@]} -eq 0 ]] || bad_options=1
			options+=( "${token}" )
		else
			files+=( "${token}" )
		fi
	done

	[[ -n ${bad_options} ]] && die "${FUNCNAME}: options must be specified before file arguments"
	[[ ${#files[@]} -eq 0 ]] && die "${FUNCNAME}: no patches or directories specified"

	__shopt_push -s nullglob
	__var_push LC_COLLATE=POSIX

	local -a paths patches
	local path f
	for path in "${files[@]}"; do
		if [[ -d ${path} ]]; then
			for f in "${path}"/*; do
				[[ -f ${f} ]] && [[ ${f} == *.diff || ${f} == *.patch ]] && paths+=( "${f}" )
			done
			[[ ${#paths[@]} -eq 0 ]] && die "${FUNCNAME}: no patches in directory: ${path}"
			patches+=( "${paths[@]}" )
		else
			patches+=( "${path}" )
		fi
	done

	__var_pop
	__shopt_pop

	local ret
	for f in "${patches[@]}"; do
		[[ ! ${PKGCORE_DEBUG} -ge 1 ]] && ebegin "${f##*/}"
		__run "patch -p1 -f -s -g0 --no-backup-if-mismatch ${options[@]} -i \"${f}\""
		ret=$?
		if ! eend "${ret}"; then
			${PKGCORE_NONFATAL} && return "${ret}"
			# append error message from patch call if it exists
			local error_msg=${PKGCORE_STDERR[@]}
			[[ -n ${error_msg} ]] && error_msg=" with:\n${error_msg}"
			die "${FUNCNAME}: applying '${f##*/}' failed${error_msg}"
		fi
	done

	return 0
}

eapply_user() {
	# return if eapply_user has already been called
	local user_patches_applied=${T}/.user_patches_applied
	[[ -f ${user_patches_applied} ]] && return
	echo "${PKGCORE_USER_PATCHES[@]}" > "${user_patches_applied}"

	if [[ ${#PKGCORE_USER_PATCHES[@]} -gt 0 ]]; then
		echo
		einfo "Applying user patches"
		einfo "---------------------"
		eapply "${PKGCORE_USER_PATCHES[@]}"
		echo
	fi
}

:
