#!/bin/bash
# ebuild-daemon.bash; core ebuild processor handling code
# Copyright 2004-2011 Brian Harring <ferringb@gmail.com>
# License: BSD/GPL2


# use listen/speak for talking to the running portage instance instead of echo'ing to the fd yourself.
# this allows us to move the open fd's w/out issues down the line.
listen() {
	if ! read -u ${EBD_READ_FD} $1; then
		echo "coms error, read failed: backing out of daemon."
		exit 1
	fi
}

speak() {
	echo "$*" >&${EBD_WRITE_FD}
}
declare -rf speak
declare -r EBD_WRITE_FD EBD_READ_FD
# ensure the other side is still there.  Well, this moreso is for the python side to ensure
# loading up the intermediate funcs succeeded.
listen com
if [ "$com" != "dude?" ]; then
	echo "serv init coms failed, received $com when expecting 'dude?'"
	exit 1
fi
speak "dude!"
listen PKGCORE_BIN_PATH
[ -z "$PKGCORE_BIN_PATH" ] && { speak "empty PKGCORE_BIN_PATH;"; exit 1; }
declare -rx PKGCORE_BIN_PATH

# get our die functionality now.
if ! source "${PKGCORE_BIN_PATH}/exit-handling.lib"; then
	speak "failed sourcing exit handling functionality"
	exit 2;
fi

listen PKGCORE_PYTHON_BINARY
[ -z "$PKGCORE_PYTHON_BINARY" ] && die "empty PKGCORE_PYTHON_BINARY, bailing"
declare -rx PKGCORE_PYTHON_BINARY
listen PKGCORE_PYTHONPATH
[ -z "$PKGCORE_PYTHONPATH" ] && die "empty PKGCORE_PYTHONPATH, bailing"
declare -rx PKGCORE_PYTHONPATH

if ! source "${PKGCORE_BIN_PATH}/ebuild.lib" >&2; then
	speak "failed"
	die "failed sourcing ${PKGCORE_BIN_PATH}/ebuild.lib"
fi

if [ -n "$SANDBOX_LOG" ]; then
	listen com
	if [ "$com" != "sandbox_log?" ]; then
		echo "unknown com '$com'"
		exit 1
	fi
	speak "$SANDBOX_LOG"
	declare -rx SANDBOX_LOG="$SANDBOX_LOG" #  #="/tmp/sandbox-${P}-${PORTAGE_SANDBOX_PID}.log"
	addwrite $SANDBOX_LOG
fi

alive='1'
re="$(readonly | cut -s -d '=' -f 1 | cut -s -d ' ' -f 3)"
for x in $re; do
	if ! has $x "$DONT_EXPORT_VARS"; then
		DONT_EXPORT_VARS="${DONT_EXPORT_VARS} $x"
	fi
done
speak $re
unset x re


if ! source "${PKGCORE_BIN_PATH}/ebuild-daemon.lib" >&2; then
	speak failed
	die "failed source ${PKGCORE_BIN_PATH}/ebuild-daemon.lib"
fi

# depend's speed up.  turn on qa interceptors by default, instead of flipping them on for each depends
# call.
export QA_CONTROLLED_EXTERNALLY="yes"
enable_qa_interceptors

export PORTAGE_PRELOADED_ECLASSES=''
unset_colors


ebd_sigint_handler() {
	#set -x
	EBD_DISABLE_DIEFUNC="asdf"
	# silence ourselves as everything shuts down.
	exec 2>/dev/null
	exec 1>/dev/null
	# supress sigpipe; if we can't tell the parent to die,
	# it's already shutting us down.
	trap 'exit 2' SIGPIPE
	speak "killed"
	trap - SIGINT
	# this relies on the python side to *not* discard the killed
	exit 2
}
trap ebd_sigint_handler SIGINT

ebd_sigkill_handler() {
	#set -x
	EBD_DISABLE_DIEFUNC="asdf"
	# silence ourselves as everything shuts down.
	exec 2>/dev/null
	exec 1>/dev/null
	# supress sigpipe; if we can't tell the parent to die,
	# it's already shutting us down.
	trap 'exit 9' SIGPIPE
	speak "killed"
	trap - SIGKILL
	exit 9
}

trap ebd_sigkill_handler SIGKILL

DONT_EXPORT_FUNCS="$(declare -F | cut -s -d ' ' -f 3)"
DONT_EXPORT_VARS="${DONT_EXPORT_VARS} alive com PORTAGE_LOGFILE cont"

# finally, load the master list of pkgcore funcs. fallback to
# regenerating it if needed.
if [ -e "${PKGCORE_BIN_PATH}/dont_export_funcs.list" ]; then
	DONT_EXPORT_FUNCS="${DONT_EXPORT_FUNCS} $(<${PKGCORE_BIN_PATH}/dont_export_funcs.list)"
else
	DONT_EXPORT_FUNCS="${DONT_EXPORT_FUNCS} $("${PKGCORE_BIN_PATH}/regenerate_dont_export_func_list.bash" 2> /dev/null)"
fi

while [ "$alive" == "1" ]; do
	com=''
	listen com
	case $com in
	process_ebuild*)
		# cleanse whitespace.
		phases="$(echo ${com#process_ebuild})"
		PORTAGE_SANDBOX_PID="$PPID"
		# note the (; forks. prevents the initialized ebd env from being polluted by ebuild calls.
		(
		if [ "${phases/depend/}" == "$phases" ]; then
			disable_qa_interceptors
		fi
		line=''
		cont=0

		while [ "$cont" == 0 ]; do
			line=''
			listen line
			if [ "$line" == "start_receiving_env" ]; then
				while listen line && [ "$line" != "end_receiving_env" ]; do #[ "$line" != "end_receiving_env" ]; do
					save_IFS
					IFS=$'\0'
					eval ${line};
					val=$?;
					restore_IFS
					if [ $val != "0" ]; then
						echo "err, env receiving threw an error for '$line': $?" >&2
						speak "env_receiving_failed"
						cont=1
						break
					fi
					if [ "${on:-unset}" != "unset" ]; then
						echo "sudo = ${SUDO_COMMAND}" >&2
						declare | grep -i sudo_command >&@
						echo "disabling" >&2
						unset on
					fi
				done
				if [ "$cont" == "0" ]; then
					speak "env_received"
				fi
			elif [ "${line:0:7}" == "logging" ]; then
				PORTAGE_LOGFILE="$(echo ${line#logging})"
				speak "logging_ack"
			elif [ "${line:0:17}" == "set_sandbox_state" ]; then
				if [ $((${line:18})) -eq 0 ]; then
					export SANDBOX_DISABLED=1
				else
					export SANDBOX_DISABLED=0
					export SANDBOX_VERBOSE="no"
				fi
			elif [ "${line}" == "start_processing" ]; then
				cont=2
			else
				echo "received unknown com: $line" >&2
			fi
		done
		if [ "$cont" != 2 ]; then
			exit $cont
		else
			reset_sandbox
			if [ -n "$SANDBOX_LOG" ]; then
				addwrite $SANDBOX_LOG
				if [ -n "$PORTAGE_LOGFILE" ]; then
					addwrite "$(readlink -f "$PORTAGE_LOGFILE")"
				fi
			fi
			if [ -z $RC_NOCOLOR ]; then
				set_colors
			fi

			DONT_EXPORT_FUNCS="${DONT_EXPORT_FUNCS} ${PORTAGE_PRELOADED_ECLASSES}"
			for x in $DONT_EXPORT_FUNCS; do
				declare -fr $x &> /dev/null
			done
			for e in $phases; do
				umask 0022
				if [ -z $PORTAGE_LOGFILE ]; then
					execute_phases ${e}
					ret=$?
				else
					# why do it this way rather then the old '[ -f ${T}/.succesfull }'?
					# simple.  this allows the actual exit code to be used, rather then just stating no .success == 1 || 0
					# note this was
					# execute_phases ${e] &> >(umask 0002; tee -i -a $PORTAGE_LOGFILE)
					# less then bash v3 however hates it.  And I hate less then v3.
					# circle of hate you see.
					execute_phases ${e} 2>&1 | {
						# this applies to the subshell only.
						umask 0002
						tee -i -a $PORTAGE_LOGFILE
					}
					ret=${PIPESTATUS[0]}
				fi
				# if sandbox log exists, then there were complaints from it.
				# tell python to display the errors, then dump relevant vars for debugging.
				if [ -n "$SANDBOX_LOG" ] && [ -e "$SANDBOX_LOG" ]; then
					ret=1
					echo "sandbox exists- $SANDBOX_LOG"
					request_sandbox_summary
					echo "SANDBOX_ON:=${SANDBOX_ON:-unset}" >&2
					echo "SANDBOX_DISABLED:=${SANDBOX_DISABLED:-unset}" >&2
					echo "SANDBOX_READ:=${SANDBOX_READ:-unset}" >&2
					echo "SANDBOX_WRITE:=${SANDBOX_WRITE:-unset}" >&2
					echo "SANDBOX_PREDICT:=${SANDBOX_PREDICT:-unset}" >&2
					echo "SANDBOX_DEBUG:=${SANDBOX_DEBUG:-unset}" >&2
					echo "SANDBOX_DEBUG_LOG:=${SANDBOX_DEBUG_LOG:-unset}" >&2
					echo "SANDBOX_LOG:=${SANDBOX_LOG:-unset}" >&2
					echo "SANDBOX_ARMED:=${SANDBOX_ARMED:-unset}" >&2
				fi
				if [ "$ret" != "0" ]; then
					exit $(($ret))
				fi
			done
		fi
		)
		# post fork.  tell python if it succeeded or not.
		if [ $? != 0 ]; then
			echo "phases failed"
			speak "phases failed"
		else
			speak "phases succeeded"
		fi
		;;
	shutdown_daemon)
		alive="0"
		;;
	preload_eclass*)
		echo "preloading eclasses into funcs." >&2
		disable_qa_interceptors
		success="succeeded"
		com="${com#preload_eclass }"
		for e in ${com}; do
			x="${e##*/}"
			x="${x%.eclass}"
			echo "preloading eclass $x" >&2
			if ! bash -n "$e"; then
				echo "errors detected in '$e'" >&2
				success='failed'
				break
			fi
			y="$( < $e)"
			eval "eclass_${x}_inherit() {
				$y
			}"
		done
		speak "preload_eclass ${success}"
		unset e x y success
		enable_qa_interceptors
		export PORTAGE_PRELOADED_ECLASSES="$PORTAGE_PRELOADED_ECLASSES ${com}"
		;;
	esac
done
exit 0
