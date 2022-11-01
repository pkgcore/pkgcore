# core ebuild processor handling code

# These are functions that shouldn't be marked readonly, since they're runtime
# switchable.
PKGCORE_RUNTIME_FUNCS=( '__timed_call' )

PKGCORE_EBD_PATH=${BASH_SOURCE[0]%/*}

__set_perf_debug() {
	if [[ ${PKGCORE_DEBUG} -ge 4 || -n ${PKGCORE_PERF_DEBUG} ]]; then
		__timed_call() {
			echo "timing $*" >&2
			time "$@"
			local __ret=$?
			echo "timed  $*" >&2
			return ${__ret}
		}
	else
		__timed_call() {
			"$@"
		}
	fi
}

__set_perf_debug

# Temporary function used by the daemon, till proper die implementation is loaded.
die() {
	echo "$@" >&2
	exit 1
}

declare -rf __set_perf_debug
declare -r PKGCORE_EBD_WRITE_FD PKGCORE_EBD_READ_FD

__ebd_sigint_handler() {
	EBD_DISABLE_DIEFUNC="yes"
	# silence ourselves as everything shuts down.
	exec 2>/dev/null
	exec 1>/dev/null
	# suppress sigpipe; if we can't tell the parent to die,
	# it's already shutting us down.
	trap "exit 2" SIGPIPE
	__ebd_write_line "SIGINT"
	trap - SIGINT
	# this relies on the python side to *not* discard the killed
	exit 2
}

__ebd_sigterm_handler() {
	EBD_DISABLE_DIEFUNC="yes"
	# silence ourselves as everything shuts down.
	exec 2>/dev/null
	exec 1>/dev/null
	# suppress sigpipe; if we can't tell the parent to die,
	# it's already shutting us down.
	trap "exit 15" SIGPIPE
	__ebd_write_line "SIGTERM"
	trap - SIGTERM
	exit 15
}

__ebd_exec_main() {
	if ! source "${PKGCORE_EBD_PATH}"/ebuild-daemon-lib.bash; then
		die "failed sourcing ${PKGCORE_EBD_PATH}/ebuild-daemon-lib.bash"
	fi

	# Ensure the other side is still there, well, this moreso is for the python
	# side to ensure loading up the intermediate funcs succeeded.
	local com
	__ebd_read_line com
	if [[ ${com} != "ebd?" ]]; then
		die "serv init coms failed, received '${com}' when expecting 'ebd?'"
	fi
	__ebd_write_line "ebd!"

	# get our die functionality now.
	if ! source "${PKGCORE_EBD_PATH}"/exit-handling.bash; then
		__ebd_write_line "failed sourcing exit handling functionality"
		exit 2
	fi

	if ! source "${PKGCORE_EBD_PATH}"/isolated-functions.bash; then
		__ebd_write_line "failed sourcing isolated-functions.bash"
		exit 2
	fi

	# enable colored support as early as possible for early die() usage
	[[ -z ${NO_COLOR} ]] && __colored_output_enable

	if ! source "${PKGCORE_EBD_PATH}"/ebuild.bash; then
		__ebd_write_line "failed"
		die "failed sourcing ${PKGCORE_EBD_PATH}/ebuild.bash"
	fi

	__ebd_read_line com
	case ${com} in
		"sandbox_log?")
			if [[ ! ${SANDBOX_LOG} ]]; then
				die "sandbox enabled but no SANDBOX_LOG?!"
			fi
			__ebd_write_line "${SANDBOX_LOG}"
			declare -rx SANDBOX_LOG=${SANDBOX_LOG}
			addwrite "${SANDBOX_LOG}"
			;;
		no_sandbox)
			;;
		*)
			die "unknown sandbox com: '${com}'"
			;;
	esac

	__IFS_push $'\n'
	readonly_vars=( $(readonly) )
	__IFS_pop
	# extract variable names from declarations
	readonly_vars=( "${readonly_vars[@]/%=*/}" )
	readonly_vars=( "${readonly_vars[@]/#* * /}" )

	for x in "${readonly_vars[@]}"; do
		if ! __safe_has "${x}" "${PKGCORE_BLACKLIST_VARS[@]}"; then
			PKGCORE_BLACKLIST_VARS+=( ${x} )
		fi
	done
	__ebd_write_line ${readonly_vars[@]}
	unset -v x readonly_vars

	# protect ourselves
	declare -rx PKGCORE_EBD_PATH=${PKGCORE_EBD_PATH}

	declare -A PKGCORE_PRELOADED_ECLASSES

	trap __ebd_sigint_handler SIGINT
	trap __ebd_sigterm_handler SIGTERM

	# finally, load the master list of pkgcore funcs. fallback to
	# regenerating it if needed.
	if [[ -f ${PKGCORE_EBD_PATH}/generated/funcs/global ]]; then
		PKGCORE_BLACKLIST_FUNCS+=( $(<"${PKGCORE_EBD_PATH}"/generated/funcs/global) )
	else
		PKGCORE_BLACKLIST_FUNCS+=( $("${PKGCORE_EBD_PATH}"/generate_global_func_list 2> /dev/null) )
	fi
	[[ $? -eq 0 ]] || die "failed reading the global function skip list"

	for x in "${PKGCORE_BLACKLIST_FUNCS[@]}"; do
		__is_function "${x}" || continue
		if ! __safe_has "${x}" "${PKGCORE_RUNTIME_FUNCS[@]}"; then
			declare -fr ${x} &> /dev/null
		fi
	done
	unset -v x

	source "${PKGCORE_EBD_PATH}"/eapi/depend.bash || die "failed sourcing eapi/depend.bash"
	__ebd_main_loop
	exit 0
}

__ebd_process_sandbox_results() {
	if [[ -z ${SANDBOX_LOG} || ! -e ${SANDBOX_LOG} ]]; then
		return 0;
	fi
	echo "sandbox exists- ${SANDBOX_LOG}" >&2
	__request_sandbox_summary >&2
	echo "SANDBOX_ON:=${SANDBOX_ON:-unset}" >&2
	echo "SANDBOX_DISABLED:=${SANDBOX_DISABLED:-unset}" >&2
	echo "SANDBOX_READ:=${SANDBOX_READ:-unset}" >&2
	echo "SANDBOX_WRITE:=${SANDBOX_WRITE:-unset}" >&2
	echo "SANDBOX_PREDICT:=${SANDBOX_PREDICT:-unset}" >&2
	echo "SANDBOX_DEBUG:=${SANDBOX_DEBUG:-unset}" >&2
	echo "SANDBOX_DEBUG_LOG:=${SANDBOX_DEBUG_LOG:-unset}" >&2
	echo "SANDBOX_LOG:=${SANDBOX_LOG:-unset}" >&2
	echo "SANDBOX_ARMED:=${SANDBOX_ARMED:-unset}" >&2
	return 1
}

__ebd_process_ebuild_phases() {
	# note that this is entirely subshelled; as such exit is used rather than returns
	(
	declare -r PKGCORE_QA_SUPPRESSED=false
	local phases=$@
	local is_depends=true
	if [[ ${phases/depend} == ${phases} ]]; then
		is_depends=false
	fi
	local cont=0

	while [[ ${cont} == 0 ]]; do
		local line=''
		__ebd_read_line line
		case ${line} in
			start_receiving_env*)
				line=${line#start_receiving_env }
				case ${line} in
					file*)
						line=${line#file }
						source "${line}"
						cont=$?
						;;
					bytes*)
						line=${line#bytes }
						__ebd_read_size "${line}" line
						__IFS_push $'\0'
						eval "${line}"
						cont=$?
						__IFS_pop
						;;
					lines|*)
						while __ebd_read_line line && [[ ${line} != "end_receiving_env" ]]; do
							__IFS_push $'\0'
							eval "${line}"
							cont=$?
							__IFS_pop
							if [[ ${cont} != 0 ]]; then
								echo "err, env receiving threw an error for '${line}': $?" >&2
								break
							fi
						done
						;;
				esac
				if [[ ${cont} != 0 ]]; then
					__ebd_write_line "env_receiving_failed"
					exit 1
				fi
				__set_perf_debug
				__ebd_write_line "env_received"
				;;
			logging*)
				PORTAGE_LOGFILE=${line#logging }
				__ebd_write_line "logging_ack"
				;;
			set_sandbox_state*)
				if [[ $(( ${line:18} )) -eq 0 ]]; then
					export SANDBOX_DISABLED=1
				else
					export SANDBOX_DISABLED=0
					export SANDBOX_VERBOSE="no"
				fi
				;;
			start_processing)
				if ${is_depends} && [[ -n ${PKGCORE_METADATA_PATH} ]]; then
					export PATH=${PKGCORE_METADATA_PATH}
				fi
				cont=2
				;;
			shutdown_daemon)
				break
				;;
			alive)
				__ebd_write_line "yep!"
				;;
			*)
				die "unknown phase processing com: '${line}'"
				;;
		esac
	done
	if [[ ${cont} != 2 ]]; then
		exit ${cont}
	fi

	[[ -n ${PORTAGE_LOGFILE} ]] && addwrite "$(readlink -f "${PORTAGE_LOGFILE}")"

	[[ -n ${PORTAGE_TMPDIR} ]] && {
		addpredict "${PORTAGE_TMPDIR}"
		addwrite "${PORTAGE_TMPDIR}"
		addread "${PORTAGE_TMPDIR}"
	}

	local ret
	umask 0022

	if [[ -z ${PORTAGE_LOGFILE} ]]; then
		__execute_phases ${phases}
		ret=$?
	else
		__execute_phases ${phases} &> >(umask 0002; tee -i -a "${PORTAGE_LOGFILE}")
		ret=$?
	fi

	if [[ ${ret} -ne 0 ]]; then
		__ebd_process_sandbox_results
		exit ${ret}
	fi
	exit 0
	)
}

__ebd_process_metadata() {
	# protect the env.
	# note the local usage is redundant in light of it, but prefer to write it this
	# way so that if someone ever drops the (), it'll still not bleed out.
	(
		# Heavy QA checks (IFS, shopt, etc) are suppressed for speed
		declare -r PKGCORE_QA_SUPPRESSED=false
		# Wipe __mode; it bleeds from our parent.
		unset -v __mode
		local __data
		local __ret
		__ebd_read_size "$1" __data
		local IFS=$'\0'
		eval "$__data"
		__ret=$?
		unset -v __data
		[[ ${__ret} -ne 0 ]] && exit 1
		unset -v __ret
		local IFS=$' \t\n'

		if [[ -n ${PKGCORE_METADATA_PATH} ]]; then
			export PATH=${PKGCORE_METADATA_PATH}
		fi

		# invoked internally by bash on PATH search failure, see the bash man
		# page section on command execution for details
		command_not_found_handle() {
			die "external commands disallowed during metadata regen: '${*}'"
		}

		__execute_phases "${2:-depend}" && exit 0
		__ebd_process_sandbox_results
		exit 1
	)
}

__make_preloaded_eclass_func() {
	eval "__preloaded_eclass_$1() {
		$2
	}"
	PKGCORE_PRELOADED_ECLASSES[$1]=__preloaded_eclass_$1
}

__ebd_main_loop() {
	PKGCORE_BLACKLIST_VARS+=( __mode com is_depends phases line cont )
	SANDBOX_ON=1
	while :; do
		local com=''
		# If we don't manage to read, this means that the other end hung up.
		# exit.
		__ebd_read_line_nonfatal com || com="shutdown_daemon"
		case ${com} in
			process_ebuild*)
				# cleanse whitespace.
				local phases=$(echo ${com#process_ebuild})
				__ebd_process_ebuild_phases ${phases}
				if [[ $? -eq 0 ]]; then
					__ebd_write_line "phases succeeded"
				else
					__ebd_write_line "phases failed ebd::${com% *} failed"
				fi
				;;
			shutdown_daemon)
				break
				;;
			preload_eclass\ *)
				success="succeeded"
				com=${com#preload_eclass }
				for e in ${com}; do
					x=${e##*/}
					x=${x%.eclass}
					if ! $(type -P bash) -n "${e}"; then
						echo "errors detected in '${e}'" >&2
						success='failed'
						break
					fi
					__make_preloaded_eclass_func "${x}" "$(< "${e}")"
				done
				__ebd_write_line "preload_eclass ${success}"
				unset -v e x success
				;;
			clear_preloaded_eclasses)
				unset -v PKGCORE_PRELOADED_ECLASSES
				declare -A PKGCORE_PRELOADED_ECLASSES
				__ebd_write_line "clear_preloaded_eclasses succeeded"
				;;
			set_metadata_path\ *)
				line=${com#set_metadata_path }
				__ebd_read_size "${line}" PKGCORE_METADATA_PATH
				__ebd_write_line "metadata_path_received"
				;;
			gen_metadata\ *|gen_ebuild_env\ *)
				local __mode="depend"
				local error_output
				[[ ${com} == gen_ebuild_env* ]] && __mode="generate_env"
				line=${com#* }
				# capture sourcing stderr output
				error_output=$(__ebd_process_metadata "${line}" "${__mode}" 2>&1 1>/dev/null)
				if [[ $? -eq 0 ]]; then
					__ebd_write_line "phases succeeded"
				else
					[[ -n ${error_output} ]] || error_output="ebd::${com% *} failed"
					__ebd_write_line "phases failed ${error_output}"
				fi
				;;
			alive)
				__ebd_write_line "yep!"
				;;
			*)
				die "unknown ebd com: '${com}'"
				;;
		esac
	done
}

# start the daemon if requested
[[ $1 == "daemonize" ]] && __ebd_exec_main

:
