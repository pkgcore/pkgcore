#!/bin/bash
# ebuild-daemon.bash; core ebuild processor handling code
# Copyright 2004-2011 Brian Harring <ferringb@gmail.com>
# License: BSD/GPL2

# use ebd_read/ebd_write for talking to the running portage instance instead of echo'ing to the fd yourself.
# this allows us to move the open fd's w/out issues down the line.
ebd_read_line()
{
	if ! read -u ${PKGCORE_EBD_READ_FD} $1; then
		echo "coms error, read failed: backing out of daemon."
		exit 1
	fi
}

# are we running a version of bash (4.1 or so) that does -N?
if echo 'y' | read -N 1 &> /dev/null; then
	ebd_read_size()
	{
		if ! read -u ${PKGCORE_EBD_READ_FD} -r -N $1 $2; then
			echo "coms error, read failed: backing out of daemon."
			exit 1;
		fi
	}

else
	# fallback to a *icky icky* but working alternative.
	ebd_read_size()
	{
		eval "${2}=\$(dd bs=1 count=$1 <&${PKGCORE_EBD_READ_FD} 2> /dev/null)"
		if [[ $? != 0 ]]; then
			echo "coms error, read failed: backing out of daemon."
			exit 1;
		fi
	}
fi

ebd_read_cat_size()
{
	dd bs=$1 count=1 <&${PKGCORE_EBD_READ_FD}
}

ebd_write_line()
{
	echo "$*" >&${PKGCORE_EBD_WRITE_FD}
}


for x in ebd_read_{line,{cat_,}size} ebd_write_line; do
	declare -rf ${x}
done
unset x
# protection for upgrading across pkgcore 0.7.7
if [ -z "${PKGCORE_EBD_WRITE_FD}" ]; then
	PKGCORE_EBD_WRITE_FD="${EBD_WRITE_FD}"
	PKGCORE_EBD_READ_FD="${EBD_READ_FD}"
	unset EBD_WRITE_FD EBD_READ_FD
fi
declare -r PKGCORE_EBD_WRITE_FD PKGCORE_EBD_READ_FD

ebd_sigint_handler()
{
	EBD_DISABLE_DIEFUNC="asdf"
	# silence ourselves as everything shuts down.
	exec 2>/dev/null
	exec 1>/dev/null
	# supress sigpipe; if we can't tell the parent to die,
	# it's already shutting us down.
	trap 'exit 2' SIGPIPE
	ebd_write_line "killed"
	trap - SIGINT
	# this relies on the python side to *not* discard the killed
	exit 2
}

ebd_sigkill_handler()
{
	EBD_DISABLE_DIEFUNC="asdf"
	# silence ourselves as everything shuts down.
	exec 2>/dev/null
	exec 1>/dev/null
	# supress sigpipe; if we can't tell the parent to die,
	# it's already shutting us down.
	trap 'exit 9' SIGPIPE
	ebd_write_line "killed"
	trap - SIGKILL
	exit 9
}


pkgcore_ebd_exec_main()
{
	# ensure the other side is still there.  Well, this moreso is for the python side to ensure
	# loading up the intermediate funcs succeeded.
	ebd_read_line com
	if [ "$com" != "dude?" ]; then
		echo "serv init coms failed, received $com when expecting 'dude?'"
		exit 1
	fi
	ebd_write_line "dude!"
	ebd_read_line PKGCORE_BIN_PATH
	[ -z "$PKGCORE_BIN_PATH" ] && { ebd_write_line "empty PKGCORE_BIN_PATH;"; exit 1; }

	# get our die functionality now.
	if ! source "${PKGCORE_BIN_PATH}/exit-handling.lib"; then
		ebd_write_line "failed sourcing exit handling functionality"
		exit 2;
	fi

	# get our die functionality now.
	if ! source "${PKGCORE_BIN_PATH}/isolated-functions.lib"; then
		ebd_write_line "failed sourcing isolated-functions.lib"
		exit 2;
	fi

	ebd_read_line PKGCORE_PYTHON_BINARY
	[ -z "$PKGCORE_PYTHON_BINARY" ] && die "empty PKGCORE_PYTHON_BINARY, bailing"
	ebd_read_line PKGCORE_PYTHONPATH
	[ -z "$PKGCORE_PYTHONPATH" ] && die "empty PKGCORE_PYTHONPATH, bailing"

	if ! source "${PKGCORE_BIN_PATH}/ebuild.lib" >&2; then
		ebd_write_line "failed"
		die "failed sourcing ${PKGCORE_BIN_PATH}/ebuild.lib"
	fi

	if [ -n "$SANDBOX_LOG" ]; then
		ebd_read_line com
		if [ "$com" != "sandbox_log?" ]; then
			echo "unknown com '$com'"
			exit 1
		fi
		ebd_write_line "$SANDBOX_LOG"
		declare -rx SANDBOX_LOG="$SANDBOX_LOG"
		addwrite $SANDBOX_LOG
	fi

	re="$(readonly | cut -s -d '=' -f 1 | cut -s -d ' ' -f 3)"
	for x in $re; do
		if ! has $x "$DONT_EXPORT_VARS"; then
			DONT_EXPORT_VARS="${DONT_EXPORT_VARS} $x"
		fi
	done
	ebd_write_line $re
	unset x re


	# protect ourselves.
	declare -rx PKGCORE_BIN_PATH="${PKGCORE_BIN_PATH}"
	declare -rx PKGCORE_PYTHON_BINARY="${PKGCORE_PYTHON_BINARY}"
	declare -rx PKGCORE_PYTHONPATH="${PKGCORE_PYTHONPATH}"

	if ! source "${PKGCORE_BIN_PATH}/ebuild-daemon.lib" >&2; then
		ebd_write_line failed
		die "failed source ${PKGCORE_BIN_PATH}/ebuild-daemon.lib"
	fi

	unset_colors
	declare -A PKGCORE_PRELOADED_ECLASSES

	trap ebd_sigint_handler SIGINT
	trap ebd_sigkill_handler SIGKILL

	# finally, load the master list of pkgcore funcs. fallback to
	# regenerating it if needed.
	if [ -e "${PKGCORE_BIN_PATH}/dont_export_funcs.list" ]; then
		DONT_EXPORT_FUNCS="${DONT_EXPORT_FUNCS} $(<${PKGCORE_BIN_PATH}/dont_export_funcs.list)"
	else
		DONT_EXPORT_FUNCS="${DONT_EXPORT_FUNCS} $("${PKGCORE_BIN_PATH}/regenerate_dont_export_func_list.bash" 2> /dev/null)"
	fi


	DONT_EXPORT_FUNCS="${DONT_EXPORT_FUNCS} ${PORTAGE_PRELOADED_ECLASSES}"
	for x in $DONT_EXPORT_FUNCS; do
		is_function $x && declare -fr $x &> /dev/null
	done
	unset x

	# depend's speed up.  turn on qa interceptors by default, instead of flipping them on for each depends;
	# same for loading depends .lib
	# important- this needs be loaded after the declare -fr so it doesn't get marked as readonly.
	# call.
	export QA_CONTROLLED_EXTERNALLY="yes"
	enable_qa_interceptors

	source "${PKGCORE_BIN_PATH}/eapi/depend.lib" >&2 || die "failed sourcing eapi/depend.lib"
	pkgcore_ebd_main_loop
	exit 0
}

ebd_process_sandbox_results()
{
	if [[ -z $SANDBOX_LOG ]] || [[ ! -e $SANDBOX_LOG ]]; then
		return 0;
	fi
	echo "sandbox exists- $SANDBOX_LOG" >&2
	request_sandbox_summary >&2
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

pkgcore_ebd_process_ebuild_phases()
{
	# note that this is entirely subshelled; as such exit is used rather than returns
	(
	declare -r PKGCORE_QA_SUPPRESSED=false
	local phases="$@"
	local is_depends=true
	if [[ ${phases/depend} == $phases ]]; then
		is_depends=false
		disable_qa_interceptors
	fi
	local cont=0

	while [ "$cont" == 0 ]; do
		local line=''
		ebd_read_line line
		case "$line" in
		start_receiving_env*)
			line="${line#start_receiving_env }"
			case "$line" in
			bytes*)
				line="${line#bytes }"
				ebd_read_size ${line} line
				pkgcore_IFS_push $'\0'
				eval "$line"
				cont=$?
				pkgcore_IFS_pop
				;;
			lines)
				;&
			*)
				while ebd_read_line line && [ "$line" != "end_receiving_env" ]; do
					pkgcore_IFS_push $'\0'
					eval ${line};
					cont=$?;
					pkgcore_IFS_pop
					if [[ $cont != 0 ]]; then
						echo "err, env receiving threw an error for '$line': $?" >&2
						break
					fi
				done
				;;
			esac
			if [[ $cont != 0 ]]; then
				ebd_write_line "env_receiving_failed"
				exit 1
			fi
			ebd_write_line "env_received"
			;;
		logging*)
			PORTAGE_LOGFILE="$(echo ${line#logging})"
			ebd_write_line "logging_ack"
			;;
		set_sandbox_state*)
			if [[ $((${line:18})) -eq 0 ]]; then
				export SANDBOX_DISABLED=1
			else
				export SANDBOX_DISABLED=0
				export SANDBOX_VERBOSE="no"
			fi
			;;
		start_processing)
			if ${is_depends} && [[ -n ${PKGCORE_METADATA_PATH} ]]; then
				export PATH="${PKGCORE_METADATA_PATH}"
			fi
			cont=2
			;;
		*)
			echo "received unknown com during phase processing: line was: $line" >&2
			;;
		esac
	done
	if [[ $cont != 2 ]]; then
		exit $cont
	fi

	[[ -n $PORTAGE_LOGFILE ]] && addwrite "$(readlink -f "$PORTAGE_LOGFILE")"

	if [[ -z $RC_NOCOLOR ]]; then
		set_colors
	fi

	[[ -n $PORTAGE_TMPDIR ]] && {
		addpredict "${PORTAGE_TMPDIR}"
		addwrite "${PORTAGE_TMPDIR}"
		addread "${PORTAGE_TMPDIR}"
	}

	umask 0022
	if [ -z $PORTAGE_LOGFILE ]; then
		execute_phases ${phases}
		ret=$?
	else
		# why do it this way rather then the old '[ -f ${T}/.succesfull }'?
		# simple.  this allows the actual exit code to be used, rather then just stating no .success == 1 || 0
		# note this was
		# execute_phases ${phases} &> >(umask 0002; tee -i -a $PORTAGE_LOGFILE)
		# less then bash v3 however hates it.  And I hate less then v3.
		# circle of hate you see.
		execute_phases ${phases} 2>&1 | {
			# this applies to the subshell only.
			umask 0002
			tee -i -a $PORTAGE_LOGFILE
		}

		ret=${PIPESTATUS[0]}
	fi

	if [[ $ret != 0 ]]; then
		ebd_process_sandbox_results
		exit $(( $ret ))
	fi
	exit 0
	)
}

ebd_process_metadata()
{
	# protect the env.
	# note the local usage is redunant in light of it, but prefer to write it this
	# way so that if someone ever drops the (), it'll still not bleed out.
	(
	# Heavy QA checks (IFS, shopt, etc) are suppressed for speed
	declare -r PKGCORE_QA_SUPPRESSED=true
	local size=$1
	local data
	local ret
	ebd_read_size $1 data
	pkgcore_IFS_push $'\0'
	eval "$data"
	ret=$?
	pkgcore_IFS_pop
	[[ $ret != 0 ]] && exit 1

	if ${is_depends} && [[ -n ${PKGCORE_METADATA_PATH} ]]; then
		export PATH="${PKGCORE_METADATA_PATH}"
	fi

	PORTAGE_SANDBOX_PID="$PPID"
	execute_phases depend && exit 0
	ebd_process_sandbox_results
	exit 1
	)
}

pkgcore_ebd_main_loop()
{
	DONT_EXPORT_VARS="${DONT_EXPORT_VARS} alie com phases line cont DONT_EXPORT_FUNCS"
	SANDBOX_ON=1
	while :; do
		local com=''
		ebd_read_line com
		case $com in
		process_ebuild*)
			# cleanse whitespace.
			local phases="$(echo ${com#process_ebuild})"
			PORTAGE_SANDBOX_PID="$PPID"
			pkgcore_ebd_process_ebuild_phases ${phases}
			# tell python if it succeeded or not.
			if [[ $? != 0 ]]; then
				ebd_write_line "phases failed"
			else
				ebd_write_line "phases succeeded"
			fi
			;;
		shutdown_daemon)
			break
			;;
		preload_eclass\ *)
			success="succeeded"
			com="${com#preload_eclass }"
			for e in ${com}; do
				x="${e##*/}"
				x="${x%.eclass}"
				if ! $(type -P bash) -n "$e"; then
					echo "errors detected in '$e'" >&2
					success='failed'
					break
				fi
				eval "pkgcore_eclass_${x}_inherit() {
					$( < $e )
				}"
				PKGCORE_PRELOADED_ECLASSES[${x}]="pkgcore_eclass_${x}_inherit"
				DONT_EXPORT_FUNCS="${DONT_EXPORT_FUNCS} pkgcore_eclass_${x}_inherit"
			done
			ebd_write_line "preload_eclass ${success}"
			unset e x success
			;;
		set_metadata_path\ *)
			line=${com#set_metadata_path }
			ebd_read_size ${line} PKGCORE_METADATA_PATH
			ebd_write_line "metadata_path_received"
			;;
		gen_metadata\ *)
			line=${com#gen_metadata }
			if ebd_process_metadata ${line}; then
				ebd_write_line "phases succeeded"
			else
				ebd_write_line "phases failed"
			fi
			;;
		*)
			echo "received unknown com: $line" >&2
			;;
		esac
	done
}

[[ -z $PKGCORE_SOURCING_FOR_REGEN_FUNCS_LIST ]] && pkgcore_ebd_exec_main

:
