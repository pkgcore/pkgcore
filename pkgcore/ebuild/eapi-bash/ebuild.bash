#!/bin/bash
# ebuild.bash; ebuild phase processing, env handling
# Copyright 2005-2011 Brian Harring <ferringb@gmail.com>: BSD/GPL2

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

ORIG_VARS=`declare | grep -E '^[^[:space:]{}()]+=' | cut -s -d '=' -f 1`
ORIG_FUNCS=`declare -F | cut -s -d ' ' -f 3`

DONT_EXPORT_FUNCS='portageq speak assert die diefunc'

DONT_EXPORT_VARS="ORIG_VARS GROUPS ORIG_FUNCS FUNCNAME DAEMONIZED CCACHE.* DISTCC.* SYNC
(TMP)?DIR FEATURES CONFIG_PROTECT.* WORKDIR RSYNC_.* GENTOO_MIRRORS
(DIST|FILES|RPM|ECLASS)DIR HOME MUST_EXPORT_ENV QA_CONTROLLED_EXTERNALLY COLORTERM HOSTNAME
myarg SANDBOX_.* BASH.* EUID PPID SHELLOPTS UID ACCEPT_(KEYWORDS|LICENSE) BUILD(_PREFIX|DIR) T DIRSTACK
DISPLAY (PKGCORE_)?EBUILD_PHASE PORTAGE_.* SUDO_.* LD_PRELOAD ret line phases D IMAGE
PORT(_LOGDIR|DIR(_OVERLAY)?) ROOT TERM _ done e PROFILE_.* EBUILD ECLASS LINENO
HILITE TMP HISTCMD OPTIND RANDOM (OLD)?PWD PKGCORE_DOMAIN IFS BASHOPTS PKGCORE_DEBUG USER PIPESTATUS LINENO FUNCNAME _pipestatus
SHELL"


if [ -z "$PKGCORE_BIN_PATH" ]; then
	echo "PKGCORE_BIN_PATH is unset!"
	exit 1
fi

# knock the sandbox vars back to the pkgs defaults.
reset_sandbox() {
	export SANDBOX_ON="1"
	export SANDBOX_PREDICT="${SANDBOX_PREDICT:+${SANDBOX_PREDICT}:}/proc/self/maps:/dev/console:/dev/random:${PORTAGE_TMPDIR}"
	export SANDBOX_WRITE="${SANDBOX_WRITE:+${SANDBOX_WRITE}:}/dev/shm:${PORTAGE_TMPDIR}"
	export SANDBOX_READ="${SANDBOX_READ:+${SANDBOX_READ}:}/dev/shm:${PORTAGE_TMPDIR}"
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

alias save_IFS='[ "${IFS:-unset}" != "unset" ] && portage_old_IFS="${IFS}"'
alias restore_IFS='if [ "${portage_old_IFS:-unset}" != "unset" ]; then IFS="${portage_old_IFS}"; unset portage_old_IFS; else unset IFS; fi'

# gentoo bug 309369; nasty alias, but it exists due to portage using declare's in env dumping.  declare statements are implicitly local.
# as such, the sourcing statement has to be in the same scope as the invoker of load_environ for that scope to get the changes
alias load_environ='{
	[ -z "${TARGET_ENV}" ] && die "load_environ was invoked w/out TARGET_ENV set";
	[ -z "${T}" ] && die "init_environ requires \$T to be set";
	EXISTING_PATH=${PATH};
	scrub_environ "${TARGET_ENV}";source "${T}/.scrubbed-env" >&2 || die "sourcing scrubbed env failed";
	pkgcore_ensure_PATH "${EXISTING_PATH}";
	unset -v EXISTING_PATH;
}'

alias init_environ='{
    EXISTING_PATH=${PATH};
    eval "$(generate_initial_ebuild_environ)" || die "failed loading initialized environment";
	pkgcore_ensure_PATH "${EXISTING_PATH}";
	unset -v EXISTING_PATH;
}'

shopt -s extdebug &> /dev/null

#if no perms are specified, dirs/files will have decent defaults
#(not secretive, but not stupid)
umask 022

# the sandbox is disabled by default except when overridden in the relevant stages
export SANDBOX_ON="0"

# ensure the passed in PATH has its components in $PATH
pkgcore_ensure_PATH()
{
	local EXISTING_PATH="$1"
	local adds
	# note this isolates the adds in the same order they appear in
	# the passed in path, maintaining that order.
	if [ "$EXISTING_PATH" != "$PATH" ]; then
		save_IFS
		IFS=':'
		for x in ${EXISTING_PATH}; do
			# keep in mind PATH=":foon" is a valid way to say "cwd"
			[ -z "${x}" ] && continue
			if ! has ${x} ${PATH} && ! has ${x} ${adds}; then
				adds="${adds:+${adds}:}${x}"
			fi
		done
		restore_IFS
		[ -n "$adds" ] && PATH="${PATH}${PATH:+:}${adds}"
	fi
	export PATH
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
			source "${dir}/profile.bashrc" >&2
		fi
	done
	restore_IFS
	if [ -f "$PORTAGE_BASHRC" ]; then
		source "$PORTAGE_BASHRC" >&2
	fi
}

# do all profile, bashrc's, and ebuild sourcing.  Should only be called in setup phase, unless the
# env is *completely* missing, as it is occasionally for ebuilds during prerm/postrm.
generate_initial_ebuild_environ() {
	OCC="$CC"
	OCXX="$CXX"
	local EXISTING_PATH="$PATH"

	if [ "${PKGCORE_EBUILD_PHASE}" == "setup" ]; then
		#we specifically save the env so it's not stomped on by sourcing.
		#bug 51552
		export_environ "${T}/.temp_env"

		if [ "$USERLAND" == "GNU" ]; then
			local PORTAGE_SHIFTED_PATH="$PATH"
			source /etc/profile.env &>/dev/null
			pkgcore_ensure_PATH "$EXISTING_PATH"
		fi

		#restore the saved env vars.
		TARGET_ENV="${T}/.temp_env"
		if ! load_environ; then
			#this shouldn't happen.
			die "failed to load ${T}/.tmp_env- fs is readonly?"
		fi

		rm "${T}/.temp_env"
		source_profiles
	fi

	if [ "${PKGCORE_EBUILD_PHASE}" != "depend" ]; then
		[ ! -z "$OCC" ] && export CC="$OCC"
		[ ! -z "$OCXX" ] && export CXX="$OCXX"

	fi

	# if daemonized, it's already loaded these funcs.
	if [ "$DAEMONIZED" != "yes" ]; then
		source "${PKGCORE_BIN_PATH}/eapi/common.bash" >&2 || die "failed sourcing eapi/common.bash"
	fi
	SANDBOX_ON="1"
	export S=${WORKDIR}/${P}

	# Expand KEYWORDS
	# We need to turn off pathname expansion for -* in KEYWORDS and
	# we need to escape ~ to avoid tilde expansion (damn bash) :)
	set -f
	KEYWORDS="$(echo ${KEYWORDS//~/\\~})"
	set +f

	unset   IUSE   DEPEND   RDEPEND   PDEPEND
	unset E_IUSE E_DEPEND E_RDEPEND E_PDEPEND

	if [ ! -f "${EBUILD}" ]; then
		echo "bailing, ebuild not found at '$EBUILD'"
		die "EBUILD=${EBUILD}; problem is, it doesn't exist.  bye." >&2
	fi

	# XXX: temp hack to make misc broken eclasses behave, java-utils-2 for example
	# XXX: as soon as these eclasses behave, remove this.
	export DESTTREE=/usr

	source "${EBUILD}" >&2
	if [ "${PKGCORE_EBUILD_PHASE}" != "depend" ]; then
		RESTRICT="${FINALIZED_RESTRICT}"
		unset FINALIZED_RESTRICT
	fi

	[ -z "${ERRORMSG}" ] || die "${ERRORMSG}"

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

	if [ "${RDEPEND-unset}" == "unset" ]; then
		export RDEPEND="${DEPEND}"
	fi

	#add in dependency info from eclasses
	IUSE="$IUSE $E_IUSE"
	DEPEND="${DEPEND} ${E_DEPEND}"
	RDEPEND="$RDEPEND $E_RDEPEND"
	PDEPEND="$PDEPEND $E_PDEPEND"

	EAPI="${EAPI-0}"

	unset E_IUSE E_DEPEND E_RDEPEND E_PDEPEND
	pkgcore_ensure_PATH "$EXISTING_PATH"
	if [ "${PKGCORE_EBUILD_PHASE}" != "depend" ]; then
		source "${PKGCORE_BIN_PATH}/eapi/${EAPI}.bash" >&2 || die "failed sourcing eapi '${EAPI}'"
	fi
	dump_environ || die "dump_environ returned non zero"
}

# short version.  think these should be sourced via at the daemons choice, rather then defacto.
# note that exit-handling loads the die functions, thus the custom failure there.
source "${PKGCORE_BIN_PATH}/exit-handling.bash" >&2 || { echo "ERROR: failed sourcing exit-handling.bash"; exit -1; }
source "${PKGCORE_BIN_PATH}/ebuild-default-functions.bash" >&2 || die "failed sourcing ebuild-default-functions.bash"
source "${PKGCORE_BIN_PATH}/isolated-functions.bash" >&2 || die "failed sourcing stripped down functions.bash"
source "${PKGCORE_BIN_PATH}/ebuild-env-utils.bash" >&2 || die "failed sourcing ebuild-env-utils.bash"

# general func to call for phase execution.  this handles necessary env loading/dumping, and executing pre/post/dyn
# calls.
execute_phases() {
	local ret
	local PKGCORE_MUST_EXPORT_ENV
	trap "exit 2" SIGINT
	trap "exit 9" SIGQUIT
	trap 'exit 1' SIGTERM
	for myarg in $*; do
		PKGCORE_EBUILD_PHASE="$myarg"
		EBUILD_PHASE="$myarg"

		PKGCORE_MUST_EXPORT_ENV=yes

		case $EBUILD_PHASE in
		nofetch)
			init_environ
			pkg_nofetch
			PKGCORE_MUST_EXPORT_ENV=
			ret=1
			;;
		postrm)
			PKGCORE_MUST_EXPORT_ENV=
			# this is a fall thru; think of it as a select chunk w/out a break
			# we just snag these phases to turn off env saving.
			;&
		prerm|preinst|postinst|config)
			export SANDBOX_ON="0"

			TARGET_ENV="${T}/environment"
			if ! load_environ; then
				#hokay.  this sucks.
				ewarn
				ewarn "failed to load env"
				ewarn "this installed pkg may not behave correctly"
				ewarn
				sleepbeep 10
			fi

			[[ -n $PKGCORE_DEBUG ]] && set -x
			type -p pre_pkg_${EBUILD_PHASE} &> /dev/null && pre_pkg_${EBUILD_PHASE}
			if type -p dyn_${EBUILD_PHASE}; then
				dyn_${EBUILD_PHASE}
			else
				pkg_${EBUILD_PHASE}
			fi
			ret=0

			type -p post_pkg_${EBUILD_PHASE} &> /dev/null && post_pkg_${EBUILD_PHASE}
			[[ $PKGCORE_DEBUG -lt 2 ]] && set +x
			;;
		unpack|prepare|configure|compile|test|install)
			if [ "${SANDBOX_DISABLED="0"}" == "0" ]; then
				export SANDBOX_ON="1"
			else
				export SANDBOX_ON="0"
			fi

			[[ $PKGCORE_DEBUG -ge 3 ]] && set -x
			TARGET_ENV="${T}/environment"
			if ! load_environ; then
				ewarn
				ewarn "failed to load env.  This is bad, bailing."
				die "unable to load saved env for phase $EBUILD_PHASE, unwilling to continue"
			fi
			[ -z "${S}" ] && die "S was null- ${S}, path=$PATH"
			[[ -n $PKGCORE_DEBUG ]] && set -x
			type -p pre_src_${EBUILD_PHASE} &> /dev/null && pre_src_${EBUILD_PHASE}
			dyn_${EBUILD_PHASE}
			ret=0
			type -p post_src_${EBUILD_PHASE} &> /dev/null && post_src_${EBUILD_PHASE}
			[[ $PKGCORE_DEBUG -lt 2 ]] && set +x
			export SANDBOX_ON="0"
			;;
		setup|setup-binpkg)
			#pkg_setup needs to be out of the sandbox for tmp file creation;
			#for example, awking and piping a file in /tmp requires a temp file to be created
			#in /etc.  If pkg_setup is in the sandbox, both our lilo and apache ebuilds break.

			EBUILD_PHASE="setup"
			export SANDBOX_ON="0"

			# binpkgs don't need to reinitialize the env.
			if [ "$myarg"  == "setup" ]; then
				[ ! -z "${DISTCC_LOG}" ] && addwrite "$(dirname ${DISTCC_LOG})"

				local x
				# if they aren't set, then holy hell ensues.  deal.

				if has ccache $FEATURES; then
					[ -z "${CCACHE_SIZE}" ] && export CCACHE_SIZE="500M"
					ccache -M ${CCACHE_SIZE} &> /dev/null
				fi
				[[ $PKGCORE_DEBUG == 2 ]] && set -x
				init_environ
			else
				TARGET_ENV="${T}/environment"
				if ! load_environ; then
					die "failed loading saved env; at ${T}/environment"
				fi
			fi

			[[ -n $PKGCORE_DEBUG ]] && set -x
			type -p pre_pkg_setup &> /dev/null && \
				pre_pkg_setup
			pkg_setup
			ret=0;
			type -p post_pkg_setup &> /dev/null && \
				post_pkg_setup
			[[ $PKGCORE_DEBUG -lt 2 ]] && set +x

			;;
		depend)
			SANDBOX_ON="1"
			PKGCORE_MUST_EXPORT_ENV=

			if [ -z "$QA_CONTROLLED_EXTERNALLY" ]; then
				enable_qa_interceptors
			fi

			init_environ

			if [ -z "$QA_CONTROLLED_EXTERNALLY" ]; then
				disable_qa_interceptors
			fi

			speak "$(pkgcore_dump_metadata_keys)"
			;;
		*)
			export SANDBOX_ON="1"
			echo "Please specify a valid command: $EBUILD_PHASE isn't valid."
			echo
			dyn_help
			exit 1
			;;
		esac

		if [[ -n ${PKGCORE_MUST_EXPORT_ENV} ]]; then
			export_environ "${T}/environment"
		fi
		[[ $PKGCORE_DEBUG -lt 4 ]] && set +x
	done
	return ${ret:-0}
}

pkgcore_dump_metadata_keys() {
	set -f
	[ "${DEPEND:-unset}" != "unset" ] && 		echo "key DEPEND=$(echo $DEPEND)"
	[ "${RDEPEND:-unset}" != "unset" ] && 		echo "key RDEPEND=$(echo $RDEPEND)"
	[ "$SLOT:-unset}" != "unset" ] && 			echo "key SLOT=$(echo $SLOT)"
	[ "$SRC_URI:-unset}" != "unset" ] && 		echo "key SRC_URI=$(echo $SRC_URI)"
	[ "$RESTRICT:-unset}" != "unset" ] && 		echo "key RESTRICT=$(echo $RESTRICT)"
	[ "$HOMEPAGE:-unset}" != "unset" ] && 		echo "key HOMEPAGE=$(echo $HOMEPAGE)"
	[ "$LICENSE:-unset}" != "unset" ] && 		echo "key LICENSE=$(echo $LICENSE)"
	[ "$DESCRIPTION:-unset}" != "unset" ] && 	echo "key DESCRIPTION=$(echo $DESCRIPTION)"
	[ "$KEYWORDS:-unset}" != "unset" ] && 		echo "key KEYWORDS=$(echo $KEYWORDS)"
	[ "$INHERITED:-unset}" != "unset" ] && 		echo "key INHERITED=$(echo $INHERITED)"
	[ "$IUSE:-unset}" != "unset" ] && 			echo "key IUSE=$(echo $IUSE)"
	[ "$PDEPEND:-unset}" != "unset" ] && 		echo "key PDEPEND=$(echo $PDEPEND)"
	[ "$PROVIDE:-unset}" != "unset" ] && 		echo "key PROVIDE=$(echo $PROVIDE)"
	[ "$EAPI:-unset}" != "unset" ] &&			echo "key EAPI=$(echo $EAPI)"
	set +f
}

#echo, everything has been sourced.  now level the read-only's.
if [ "$*" != "daemonize" ]; then
	for x in ${DONT_EXPORT_FUNCS}; do
		declare -fr "$x" || die "failed marking ${x} func reaodnly"
	done
	unset x
fi

DONT_EXPORT_VARS="${DONT_EXPORT_VARS} $(declare | invoke_filter_env --print-vars | regex_filter_input ${ORIG_VARS} ${DONT_EXPORT_VARS})"

[ -z "${ORIG_FUNCS}" ] && DONT_EXPORT_FUNCS="${DONT_EXPORT_FUNCS} $(declare -F | cut -s -d ' ' -f 3)"
set +f

export XARGS
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
:
