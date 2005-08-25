#!/bin/bash
# ebuild.sh; ebuild phase processing, env handling
# Copyright 2004-2005 Gentoo Foundation
# Distributed under the terms of the GNU General Public License v2
# $Header: /var/cvsroot/gentoo-src/portage/bin/ebuild.sh,v 1.214 2005/08/05 02:37:14 vapier Exp $

# general phase execution path-
# execute_phases is called, which sets EBUILD_PHASE, and then depending on the phase, 
# loads or initializes.  Env is init'd for non src based stages if the env isn't found- otherwise
# it loads the environ via load_environ call.  In cases where env isn't found for phases setup -> merge,
# it bails (theres no way the env should be missing- exemption is setup phase).
# 
# for env filtering for restoration and reloading, note the updates to DONT_EXPORT_(VARS|FUNCS).
# those vars are basically used to track what shouldn't be saved/restored.  Whitespace seperated,
# those vars can support posix (think egrep) regex.  They should hold all vars/funcs that are internal
# ebuild.sh vars.  Basically, filter all vars/funcs that are specific to ebuild.sh, not the ebuild.
# 
# after loading the env, user defined pre hooks are executed, dyn_${EBUILD_PHASE} is executed, 
# and the post hooks are executed.  If the env needs to be flushed to disk, MUST_EXPORT_ENV is set to 
# "yes", and execute_phases will dump it to ${T}/environment.
#
# few notes on general env stuff- if it's not ebuild specific or a user option, it's typically marked
# readonly.  This limits users, but also helps to ensure that reloaded envs from older portages don't
# overwrite an internal ebd.sh function that has since changed.

ORIG_VARS=`declare | egrep '^[^[:space:]{}()]+=' | cut -s -d '=' -f 1`
ORIG_FUNCS=`declare -F | cut -s -d ' ' -f 3`
DONT_EXPORT_FUNCS='portageq speak'
DONT_EXPORT_VARS="ORIG_VARS GROUPS ORIG_FUNCS FUNCNAME DAEMONIZED CCACHE.* DISTCC.* AUTOCLEAN CLEAN_DELAY SYNC
(TMP|)DIR FEATURES CONFIG_PROTECT.* (P|)WORKDIR (FETCH|RESUME) COMMAND RSYNC_.* GENTOO_MIRRORS 
(DIST|FILES|RPM|ECLASS)DIR HOME MUST_EXPORT_ENV QA_CONTROLLED_EXTERNALLY COLORTERM COLS ROWS HOSTNAME
myarg SANDBOX_.* BASH.* EUID PPID SHELLOPTS UID ACCEPT_(KEYWORDS|LICENSE) BUILD(_PREFIX|DIR) T DIRSTACK
DISPLAY (EBUILD|)_PHASE PORTAGE_.* RC_.* SUDO_.* IFS PATH LD_PRELOAD ret line phases D EMERGE_FROM
PORT(_LOGDIR|DIR(|_OVERLAY)) ROOT TERM _ done e ENDCOLS PROFILE_.* BRACKET BAD WARN GOOD NORMAL"
# flip this on to enable extra noisy output for debugging.
#DEBUGGING="yes"

# XXX: required for migration from .51 to this.
if [ -z "$PORTAGE_BIN_PATH" ]; then
	declare -rx PORTAGE_BIN_PATH="/usr/lib/portage/bin"
fi

# knock the sandbox vars back to the defaults.
reset_sandbox() {
	export SANDBOX_ON="1"
	export SANDBOX_PREDICT="${SANDBOX_PREDICT:+${SANDBOX_PREDICT}:}/proc/self/maps:/dev/console:/usr/lib/portage/pym:/dev/random"
	export SANDBOX_WRITE="${SANDBOX_WRITE:+${SANDBOX_WRITE}:}/dev/shm"
	export SANDBOX_READ="${SANDBOX_READ:+${SANDBOX_READ}:}/dev/shm"
	local s
	for x in CCACHE_DIR DISTCC_DIR D WORKDIR T; do
		if [ -n "${!x}" ]; then
			addread  "${!x}"
			addwrite "${!x}"
		fi
	done
}

# Prevent aliases from causing portage to act inappropriately.
# Make sure it's before everything so we don't mess aliases that follow.
unalias -a

# We need this next line for "die" and "assert". It expands 
# It _must_ preceed all the calls to die and assert.
shopt -s expand_aliases

# Unset some variables that break things.
unset GZIP BZIP BZIP2 CDPATH GREP_OPTIONS GREP_COLOR GLOB_IGNORE

alias die='diefunc "$FUNCNAME" "$LINENO" "$?"'
alias assert='_pipestatus="${PIPESTATUS[*]}"; [[ "${_pipestatus// /}" -eq 0 ]] || diefunc "$FUNCNAME" "$LINENO" "$_pipestatus"'
alias save_IFS='[ "${IFS:-unset}" != "unset" ] && portage_old_IFS="${IFS}"'
alias restore_IFS='if [ "${portage_old_IFS:-unset}" != "unset" ]; then IFS="${portage_old_IFS}"; unset portage_old_IFS; else unset IFS; fi'

diefunc() {
        local funcname="$1" lineno="$2" exitcode="$3"
        shift 3
        echo >&2
        echo "!!! ERROR: $CATEGORY/$PF failed." >&2
        echo "!!! Function $funcname, Line $lineno, Exitcode $exitcode" >&2
        echo "!!! ${*:-(no error message)}" >&2
        echo "!!! If you need support, post the topmost build error, NOT this status message." >&2
        echo >&2
        exit 1
}

killparent() {
	trap INT
	kill ${PORTAGE_MASTER_PID}
}

convert_filter() {
	while [ -n "$1" ]; do
		echo -n "$1"
		shift
		if [ -n "$1" ]; then
			echo -n ','
		fi
	done
}

hasq() {
        local x

        local me=$1
        shift

        # All the TTY checks really only help out depend. Which is nice.
        # Logging kills all this anyway. Everything becomes a pipe. --NJ
        for x in "$@"; do
                if [ "${x}" == "${me}" ]; then
                        return 0
                fi
        done
        return 1
}

hasv() {
	if hasq "$@"; then
		echo "${1}"
		return 0
	fi
	return 1
}

#if no perms are specified, dirs/files will have decent defaults
#(not secretive, but not stupid)
umask 022

# the sandbox is disabled by default except when overridden in the relevant stages
export SANDBOX_ON="0"

gen_filter() {
	if [ "$#" == 0 ]; then 
		#default param to keep things quiet
		echo 
		return
	fi
	echo -n '('
	while [ "$1" ]; do
		echo -n "$1"
		shift
		if [ "$1" ]; then
			echo -n '|'
		fi
	done
	echo -n ')'
}

# func for beeping and delaying a defined period of time.
sleepbeep() {
	if [ ! "$#" -lt 3 ] || [ ! "$#" -gt 0 ]; then
		echo "sleepbeep requires one arg- number of beeps"
		echo "additionally, can supply a 2nd arg- interval between beeps (defaults to 0.25s"
		die "invalid call to sleepbeep"
	fi
	local count=$(($1))
	local interval="${2:-0.25}"
	while [ $count -gt 0 ]; do
		echo -en "\a";
		sleep $interval &> /dev/null
		count=$(($count - 1))
	done
	return 0
}

# basically this runs through the output of export/readonly/declare, properly handling variables w/ values 
# that have newline.
get_vars() {
	local l
	if [ "${portage_old_IFS:-unset}" != "unset" ]; then
		local portage_old_IFS
	fi
	save_IFS
	IFS=''
	while read l; do
		l="${l/=*}"
		echo "${l##* }"
	done
	restore_IFS
}

# selectively saves  the environ- specifically removes things that have been marked to not be exported.
# dump the environ to stdout.
dump_environ() {
	local f x;
	declare | filter-env -f $(convert_filter ${DONT_EXPORT_FUNCS}) -v $(convert_filter ${DONT_EXPORT_VARS} f x)

	if ! hasq "--no-attributes" "$@"; then
		echo "reinstate_loaded_env_attributes ()"
		echo "{"

		x=$(export | get_vars | egrep -v "$(gen_filter ${DONT_EXPORT_VARS} f x y)$")
		[ ! -z "$x" ] && echo "    export `echo $x`"
		

		x=$(readonly | get_vars | egrep -v "$(gen_filter ${DONT_EXPORT_VARS} f x y)")
		[ ! -z "$x" ] && echo "    readonly `echo $x`"
		

		x=$(declare -i | get_vars | egrep -v "$(gen_filter ${DONT_EXPORT_VARS} f x y)")
		[ ! -z "$x" ] && echo "    declare -i `echo $x`"

		declare -F | egrep "^declare -[aFfirtx]+ $(gen_filter ${f} )\$" | egrep -v "^declare -f "
		shopt -p
		echo "    unset reinstate_loaded_env_attributes"
		echo "}"
	fi
	
	debug-print "dumped"
	if [ ! -z ${DEBUGGING} ]; then
		echo "#dumping debug info"
		echo "#var filter..."
		echo "#$(gen_filter ${DONT_EXPORT_VARS} f x | sort)"
		echo "#func filter..."
		echo "#$(gen_filter ${DONT_EXPORT_FUNCS} | sort)"
		echo "#DONT_EXPORT_VARS follow"
		for x in `echo $DONT_EXPORT_VARS | sort`; do
			echo "#    $x";
		done
		echo ""
		echo "#DONT_EXPORT_FUNCS follow"
		for x in `echo $DONT_EXPORT_FUNCS | sort`; do
			echo "#    $x";
		done
	fi
}

# dump environ to $1, optionally piping it through $2 and redirecting $2's output to $1.
export_environ() {
	local temp_umask
	if [ "${1:-unset}" == "unset" ]; then
		die "export_environ requires at least one arguement"
	fi

	#the spaces on both sides are important- otherwise, the later ${DONT_EXPORT_VARS/ temp_umask /} won't match.
	#we use spaces on both sides, to ensure we don't remove part of a variable w/ the same name- 
	# ex: temp_umask_for_some_app == _for_some_app.  
	#Do it with spaces on both sides.

	DONT_EXPORT_VARS="${DONT_EXPORT_VARS} temp_umask "
	temp_umask=`umask`
	umask 0002

	debug-print "exporting env for ${EBUILD_PHASE} to $1, using optional post-processor '${2:-none}'"

	if [ "${2:-unset}" == "unset" ]; then
		dump_environ > "$1"
	else
		dump_environ | $2 > "$1"
	fi
	chown portage:portage "$1" &>/dev/null
	chmod 0664 "$1" &>/dev/null

	DONT_EXPORT_VARS="${DONT_EXPORT_VARS/ temp_umask /}"

	umask $temp_umask
	debug-print "exported."
}

# reload a saved env, applying usual filters to the env prior to eval'ing it.
load_environ() {
	local src e
	#protect the exterior env to some degree from older saved envs, where *everything* was dumped (no filters applied)
	local SANDBOX_STATE=$SANDBOX_ON
	local EBUILD_PHASE=$EBUILD_PHASE
	SANDBOX_ON=0

	SANDBOX_READ="/bin:${SANDBOX_READ}:/dev/urandom:/dev/random:$PORTAGE_BIN_PATH"
	SANDBOX_ON=$SANDBOX_STATE

	if [ ! -z $DEBUGGING ]; then
		echo "loading env for $EBUILD_PHASE" >&2
	fi

	if [ -n "$1" ]; then
		src="$1"
	fi
	[ ! -z $DEBUGGING ] && echo "loading environment from $src" >&2

	# XXX: note all of the *very careful* handling of bash env dumps through this code, and the fact 
	# it took 4 months to get it right.  There's a reason you can't just pipe the $(export) to a file.
	# They were implemented wrong, as I stated when the export kludge was added.
	# so we're just dropping the attributes.  .51-r4 should carry a fixed version, .51 -> .51-r3
	# aren't worth the trouble.  Drop all inline declare's that would be executed.
	# potentially handle this via filter-env?
	# ~harring
	function declare() {
		:
	}
	if [ -f "$src" ]; then
		eval "$({ [ "${src%.bz2}" != "${src}" ] && bzcat "$src" || cat "${src}"
			} | filter-env -v $(convert_filter ${DONT_EXPORT_VARS}) \
			-f $(convert_filter ${DONT_EXPORT_FUNCS}) )"
#			} | egrep -v "^$(gen_filter $DONT_EXPORT_VARS)=")"
	else
		echo "ebuild=${EBUILD}, phase $EBUILD_PHASE" >&2
		return 1
	fi
	unset declare
	return 0
}

# walk the cascaded profile src'ing it's various bashrcs.
# overriden by daemon normally.
source_profiles() {
	local dir
	save_IFS
	# XXX: Given the following unset, is this set needed?
	IFS=$'\n'
	for dir in ${PROFILE_PATHS}; do
		# Must unset it so that it doesn't mess up assumptions in the RCs.
		unset IFS
		if [ -f "${dir}/profile.bashrc" ]; then
			source "${dir}/profile.bashrc"
		fi
	done
	restore_IFS
	if [ -f "$PORTAGE_BASHRC" ]; then
		source "$PORTAGE_BASHRC"
	fi
}

# do all profile, bashrc's, and ebuild sourcing.  Should only be called in setup phase, unless the
# env is *completely* missing, as it is occasionally for ebuilds during prerm/postrm.
init_environ() {
#	echo "initializating environment" >&2
	OCC="$CC"
	OCXX="$CXX"


	# XXX this too, sucks.
#	export PATH="/sbin:/usr/sbin:/usr/lib/portage/bin:/bin:/usr/bin"
	if [ "${EBUILD_PHASE}" == "setup" ]; then
		#we specifically save the env so it's not stomped on by sourcing.
		#bug 51552
		dump_environ --no-attributes > "${T}/.temp_env"

		if [ "$USERLAND" == "GNU" ]; then
			local PORTAGE_SHIFTED_PATH="$PATH"
			source /etc/profile.env &>/dev/null
			PATH="${PORTAGE_SHIFTED_PATH:+${PORTAGE_SHIFTED_PATH}}${PATH:+:${PATH}}"
		fi
		#shift path.  I don't care about 51552, I'm not using the env's supplied path, alright? :)

		#restore the saved env vars.
		if ! load_environ "${T}/.temp_env"; then
			#this shouldn't happen.
			die "failed to load ${T}/.tmp_env- fs is readonly?"
		fi

		rm "${T}/.temp_env"
		source_profiles
	fi

	if [ "${EBUILD_PHASE}" != "depend" ]; then
		[ ! -z "$OCC" ] && export CC="$OCC"
		[ ! -z "$OCXX" ] && export CXX="$OCXX"

	fi

	export DESTTREE=/usr
	export INSDESTTREE=""
	export EXEDESTTREE=""
	export DOCDESTTREE=""
	export INSOPTIONS="-m0644"
	export EXEOPTIONS="-m0755"	
	export LIBOPTIONS="-m0644"
	export DIROPTIONS="-m0755"
	export MOPREFIX=${PN}

	# if daemonized, it's already loaded these funcs.
	if [ "$DAEMONIZED" != "yes" ]; then
		source "${PORTAGE_BIN_PATH}/ebuild-functions.sh" || die "failed sourcing ebuild-functions.sh"
	fi
	SANDBOX_ON="1"
	export S=${WORKDIR}/${P}

	# Expand KEYWORDS
	# We need to turn off pathname expansion for -* in KEYWORDS and 
	# we need to escape ~ to avoid tilde expansion (damn bash) :)
	set -f
	KEYWORDS="$(echo ${KEYWORDS//~/\\~})"
	set +f

	unset   IUSE   DEPEND   RDEPEND   CDEPEND   PDEPEND
	unset E_IUSE E_DEPEND E_RDEPEND E_CDEPEND E_PDEPEND

	if [ ! -f "${EBUILD}" ]; then
		echo "bailing, ebuild not found at '$EBUILD'"
		die "EBUILD=${EBUILD}; problem is, it doesn't exist.  bye." >&2
	fi

#	eval "$(cat "${EBUILD}"; echo ; echo 'true')" || die "error sourcing ebuild"
	source "${EBUILD}"
	if [ "${EBUILD_PHASE}" != "depend" ]; then
		RESTRICT="${PORTAGE_RESTRICT}"
		unset PORTAGE_RESTRICT
	fi

	[ -z "${ERRORMSG}" ] || die "${ERRORMSG}"

	hasq nostrip ${RESTRICT} && export DEBUGBUILD=1

	#a reasonable default for $S
	if [ "$S" = "" ]; then
		export S=${WORKDIR}/${P}
	fi

	#some users have $TMP/$TMPDIR to a custom dir in their home ...
	#this will cause sandbox errors with some ./configure
	#scripts, so set it to $T.
	export TMP="${T}"
	export TMPDIR="${T}"

	# Note: this next line is not the same as export RDEPEND=${RDEPEND:-${DEPEND}}
	# That will test for unset *or* NULL ("").  We want just to set for unset...

	#turn off glob expansion from here on in to prevent *'s and ? in the DEPEND
	#syntax from getting expanded :)  Fixes bug #1473
#	set -f
	if [ "${RDEPEND-unset}" == "unset" ]; then
		export RDEPEND="${DEPEND}"
		debug-print "RDEPEND: not set... Setting to: ${DEPEND}"
	fi

	#add in dependency info from eclasses
	IUSE="$IUSE $E_IUSE"
	DEPEND="${DEPEND} ${E_DEPEND}"
	RDEPEND="$RDEPEND $E_RDEPEND"
	CDEPEND="$CDEPEND $E_CDEPEND"
	PDEPEND="$PDEPEND $E_PDEPEND"

	unset E_IUSE E_DEPEND E_RDEPEND E_CDEPEND E_PDEPEND
#	set +f

#	declare -r DEPEND RDEPEND SLOT SRC_URI RESTRICT HOMEPAGE LICENSE DESCRIPTION
#	declare -r KEYWORDS INHERITED IUSE CDEPEND PDEPEND PROVIDE
#	echo "DONT_EXPORT_FUNCS=$DONT_EXPORT_FUNCS" >&2
}

# short version.  think these should be sourced via at the daemons choice, rather then defacto.
source "${PORTAGE_BIN_PATH}/ebuild-default-functions.sh" || die "failed sourcing ebuild-default-functions.sh"
source "${PORTAGE_BIN_PATH}/isolated-functions.sh" || die "failed sourcing stripped down functions.sh"

# general func to call for phase execution.  this handles necessary env loading/dumping, and executing pre/post/dyn
# calls.
execute_phases() {
	local ret
	for myarg in $*; do
		EBUILD_PHASE="$myarg"
		MUST_EXPORT_ENV="no"
		case $EBUILD_PHASE in
		nofetch)
			init_environ
			pkg_nofetch
			;;
		prerm|postrm|preinst|postinst|config)
			export SANDBOX_ON="0"

			if ! load_environ $PORT_ENV_FILE; then
				#hokay.  this sucks.
				ewarn 
				ewarn "failed to load env"
				ewarn "this installed pkg may not behave correctly"
				ewarn
				sleepbeep 10
			fi	

			if type reinstate_loaded_env_attributes &> /dev/null; then
				reinstate_loaded_env_attributes
			fi
			[ "$PORTAGE_DEBUG" == "1" ] && set -x
			type -p pre_pkg_${EBUILD_PHASE} &> /dev/null && pre_pkg_${EBUILD_PHASE}
			if type -p dyn_${EBUILD_PHASE}; then
				dyn_${EBUILD_PHASE}
			else
				pkg_${EBUILD_PHASE}
			fi
			ret=0
			type -p post_pkg_${EBUILD_PHASE} &> /dev/null && post_pkg_${EBUILD_PHASE}
			[ "$PORTAGE_DEBUG" == "1" ] && set +x
			;;
		clean)
			einfo "clean phase is now handled in the python side of portage."
			einfo "ebuild-daemon calls it correctly, upgrading from vanilla portage to ebd" 
			einfo "always triggers this though.  Please ignore it."
			;;
		unpack|compile|test|install)
			if [ "${SANDBOX_DISABLED="0"}" == "0" ]; then
				export SANDBOX_ON="1"
			else
				export SANDBOX_ON="0"
			fi

			if ! load_environ ${T}/environment; then
				ewarn 
				ewarn "failed to load env.  This is bad, bailing."
				die "unable to load saved env for phase $EBUILD_PHASE, unwilling to continue"
			fi
			if type reinstate_loaded_env_attributes &> /dev/null; then
#				echo "reinstating attribs" >&2
				reinstate_loaded_env_attributes
			fi
			[ "$PORTAGE_DEBUG" == "1" ] && set -x
			type -p pre_src_${EBUILD_PHASE} &> /dev/null && pre_src_${EBUILD_PHASE}
			dyn_${EBUILD_PHASE}
			ret=0
			type -p post_src_${EBUILD_PHASE} &> /dev/null && post_src_${EBUILD_PHASE}
			[ "$PORTAGE_DEBUG" == "1" ] && set +x
			export SANDBOX_ON="0"
			;;
		setup)
			#pkg_setup needs to be out of the sandbox for tmp file creation;
			#for example, awking and piping a file in /tmp requires a temp file to be created
			#in /etc.  If pkg_setup is in the sandbox, both our lilo and apache ebuilds break.

			export SANDBOX_ON="0"

			[ ! -z "${DISTCC_LOG}" ] && addwrite "$(dirname ${DISTCC_LOG})"

			local x
			# if they aren't set, then holy hell ensues.  deal.

			[ -z "${CCACHE_SIZE}" ] && export CCACHE_SIZE="500M"
			ccache -M ${CCACHE_SIZE} &> /dev/null
			init_environ
			MUST_EXPORT_ENV="yes"

			[ "$PORTAGE_DEBUG" == "1" ] && set -x
			type -p pre_pkg_${EBUILD_PHASE} &> /dev/null && pre_pkg_${EBUILD_PHASE}
			dyn_${EBUILD_PHASE}
			ret=0;
			type -p post_pkg_${EBUILD_PHASE} &> /dev/null && post_pkg_${EBUILD_PHASE}
			[ "$PORTAGE_DEBUG" == "1" ] && set +x

			;;
		depend)
			SANDBOX_ON="1"
			MUST_EXPORT_ENV="no"

			trap 'killparent' INT
			if [ -z "$QA_CONTROLLED_EXTERNALLY" ]; then
				enable_qa_interceptors
			fi

			init_environ

			if [ -z "$QA_CONTROLLED_EXTERNALLY" ]; then
				disable_qa_interceptors
			fi
			trap - INT

			set -f
			[ "${DEPEND:-unset}" != "unset" ] && 		speak "key DEPEND=$(echo $DEPEND)"
			[ "${RDEPEND:-unset}" != "unset" ] && 		speak "key RDEPEND=$(echo $RDEPEND)"
			[ "$SLOT:-unset}" != "unset" ] && 		speak "key SLOT=$(echo $SLOT)"
			[ "$SRC_URI:-unset}" != "unset" ] && 		speak "key SRC_URI=$(echo $SRC_URI)"
			[ "$RESTRICT:-unset}" != "unset" ] && 		speak "key RESTRICT=$(echo $RESTRICT)"
			[ "$HOMEPAGE:-unset}" != "unset" ] && 		speak "key HOMEPAGE=$(echo $HOMEPAGE)"
			[ "$LICENSE:-unset}" != "unset" ] && 		speak "key LICENSE=$(echo $LICENSE)"
			[ "$DESCRIPTION:-unset}" != "unset" ] && 	speak "key DESCRIPTION=$(echo $DESCRIPTION)"
			[ "$KEYWORDS:-unset}" != "unset" ] && 		speak "key KEYWORDS=$(echo $KEYWORDS)"
			[ "$INHERITED:-unset}" != "unset" ] && 		speak "key INHERITED=$(echo $INHERITED)"
			[ "$IUSE:-unset}" != "unset" ] && 		speak "key IUSE=$(echo $IUSE)"
			[ "$CDEPEND:-unset}" != "unset" ] && 		speak "key CDEPEND=$(echo $CDEPEND)"
			[ "$PDEPEND:-unset}" != "unset" ] && 		speak "key PDEPEND=$(echo $PDEPEND)"
			[ "$PROVIDE:-unset}" != "unset" ] && 		speak "key PROVIDE=$(echo $PROVIDE)"
			set +f
			;;
		*)
			export SANDBOX_ON="1"
			echo "Please specify a valid command: $EBUILD_PHASE isn't valid."
			echo
			dyn_help
			exit 1
			;;
		esac

		if [ "${MUST_EXPORT_ENV}" == "yes" ]; then
#			echo "exporting environ ${EBUILD_PHASE} to ${T}/environment" >&2
			export_environ "${T}/environment"
			MUST_EXPORT_ENV="no"
		fi
	done
	return ${ret:-0}
}

#echo, everything has been sourced.  now level the read-only's.
if [ "$*" != "daemonize" ]; then
	for x in ${DONT_EXPORT_FUNCS}; do
		declare -fr "$x"
	done
	unset x
fi

f="$(declare | { 
	read l; 
	while [ "${l% \(\)}" == "$l" ]; do
		echo "${l/=*}";
		read l;
	done;
	unset l
   })"

#update the don't export filters.
if [ -z "${ORIG_VARS}" ]; then
	DONT_EXPORT_VARS="${DONT_EXPORT_VARS} ${f}"
else
	DONT_EXPORT_VARS="${DONT_EXPORT_VARS} $(echo "${f}" | egrep -v "^`gen_filter ${ORIG_VARS}`\$")"
fi
unset f

# I see no differance here...
if [ -z "${ORIG_FUNCS}" ]; then
	DONT_EXPORT_FUNCS="${DONT_EXPORT_FUNCS} $(declare -F | cut -s -d ' ' -f 3)"
else  
	DONT_EXPORT_FUNCS="${DONT_EXPORT_FUNCS} $(declare -F | cut -s -d ' ' -f 3 )"
fi
set +f

export XARGS
if [ "$(id -nu)" == "portage" ] ; then
	export USER=portage
fi
set +H -h
# if we're being src'd for our functions, do nothing.  if called directly, define a few necessary funcs.
if [ "$*" != "daemonize" ]; then

	if [ "${*/depend}" != "$*" ]; then
		speak() {
			echo "$*" >&4
		}
		declare -rf speak
	fi
	if [ -z "${NOCOLOR}" ]; then
		set_colors
	else
		unset_colors
	fi
	unset x
	execute_phases $*
	exit 0
else
	DAEMONIZED="yes"
	export DAEMONIZED
	readonly DAEMONIZED
fi
true
