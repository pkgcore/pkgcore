PKGCORE_BANNED_FUNCS=( libopts )

dostrip() { __ebd_ipc_cmd ${FUNCNAME} "" "$@"; }
