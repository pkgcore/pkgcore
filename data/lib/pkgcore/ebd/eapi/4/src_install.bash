default_src_install() { __phase_src_install; }

docompress() { __ebd_ipc_cmd ${FUNCNAME} "" "$@"; }
