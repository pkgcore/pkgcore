eapply() { __ebd_ipc_cmd ${FUNCNAME} "" "$@"; }

eapply_user() {
	[[ -f ${T}/.user_patches_applied ]] && return
	__ebd_ipc_cmd ${FUNCNAME} "" "$@"
}

:
