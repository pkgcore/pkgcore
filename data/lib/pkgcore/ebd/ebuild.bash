# ebuild phase processing, env handling

# general phase execution path- __execute_phases is called, which sets EBUILD_PHASE, and then
# depending on the phase, loads or initializes. Env is init'd for non src based stages if the env
# isn't found- otherwise it loads the environ via __load_environ call. In cases where env isn't
# found for phases setup -> merge, it bails (theres no way the env should be missing- exemption is
# setup phase).
#
# for env filtering for restoration and reloading, note the updates to PKGCORE_BLACKLIST_(VARS|FUNCS).
# those vars are basically used to track what shouldn't be saved/restored. Whitespace separated,
# those vars can support posix (think egrep) regex. They should hold all vars/funcs that are
# internal ebd vars. Basically, filter all vars/funcs that are specific to ebd, not the ebuild.
#
# after loading the env, user defined pre hooks are executed, __dyn_${EBUILD_PHASE} is executed, and
# the post hooks are executed. If the env needs to be flushed to disk, PKGCORE_MUST_EXPORT_ENV is
# set to "yes", and __execute_phases will dump it to ${T}/environment.
#
# few notes on general env stuff- if it's not ebuild specific or a user option, it's typically
# marked readonly. This limits users, but also helps to ensure that reloaded envs from older
# portages don't overwrite an internal ebd.sh function that has since changed.

PKGCORE_BLACKLIST_VARS=(
	# bash-related
	$(compgen -v) "BASH_.*" COLUMNS OLDPWD

	# external programs
	"SANDBOX_.*" "CCACHE.*" "DISTCC.*" "SUDO_.*"

	# internals
	"___.*" "PKGCORE_.*" ret

	# portage-compat
	"PORTAGE_.*" "EMERGE_.*" FEATURES EMERGE_FROM
	"RSYNC_.*" GENTOO_MIRRORS
	"(DIST|FILES|RPM|ECLASS)DIR"
	"ACCEPT_(PROPERTIES|RESTRICT)"
	"(RESUME|FETCH)COMMAND(_.*)?" XARGS SYNC DIR
	"ACCEPT_(KEYWORDS|LICENSE)"
	"PORT(_LOGDIR|DIR(_OVERLAY)?)" "PROFILE_.*" ECLASS TMP

	# PMS
	CATEGORY PF P PN PV PR PVR EBUILD A EBUILD_PHASE
	T WORKDIR D ED ROOT EROOT EPREFIX HOME "USE_EXPAND_.*"
	MERGE_TYPE REPLACING_VERSIONS REPLACED_BY_VERSION
)

if [[ -z ${PKGCORE_EBD_PATH} ]]; then
	echo "PKGCORE_EBD_PATH is unset!"
	exit 1
fi

# knock the sandbox vars back to the pkgs defaults.
__reset_sandbox() {
	export SANDBOX_ON=1
	export SANDBOX_PREDICT=${SANDBOX_PREDICT:+${SANDBOX_PREDICT}:}/proc/self/maps:/dev/console:/dev/random:${PORTAGE_TMPDIR}
	export SANDBOX_WRITE=${SANDBOX_WRITE:+${SANDBOX_WRITE}:}/dev/shm:${PORTAGE_TMPDIR}
	export SANDBOX_READ=${SANDBOX_READ:+${SANDBOX_READ}:}/dev/shm:${PORTAGE_TMPDIR}
	local var
	for var in CCACHE_DIR DISTCC_DIR D WORKDIR T; do
		if [[ -n ${!var} ]]; then
			addread "${!var}"
			addwrite "${!var}"
		fi
	done
}

# Prevent aliases from causing portage to act inappropriately.
# Make sure it's before everything so we don't mess aliases that follow.
unalias -a

# This is needed for calling __load_environ, __load_safe_environ, and
# __init_environ. If those can ever be moved into functions this can be
# dropped.
shopt -s expand_aliases

# Unset some variables that break things.
unset -v GZIP BZIP BZIP2 CDPATH GREP_OPTIONS GREP_COLOR GLOB_IGNORE

# gentoo bug 309369; nasty alias, but it exists due to portage using declare's
# in env dumping. declare statements are implicitly local. as such, the
# sourcing statement has to be in the same scope as the invoker of
# __load_environ for that scope to get the changes
alias __load_environ='{
	[[ -z ${PKGCORE_TARGET_ENV} ]] && die "__load_environ was invoked w/out PKGCORE_TARGET_ENV set";
	[[ -z ${T} ]] && die "__load_environ requires \$T to be set";
	PKGCORE_EXISTING_PATH=${PATH};
	__timed_call __environ_sanitize_saved_env "${PKGCORE_TARGET_ENV}"
	if [[ -n ${PKGCORE_PERF_DEBUG} ]]; then
		echo "timing source ${PKGCORE_TARGET_ENV}" >&2
		time source "${PKGCORE_TARGET_ENV}" >&2
		echo "timed source ${PKGCORE_TARGET_ENV}" >&2
	else
		source "${PKGCORE_TARGET_ENV}" >&2
	fi
	[[ $? == 0 ]] || die "sourcing saved env failed";
	__ensure_PATH "${PKGCORE_EXISTING_PATH}";
	__timed_call __load_eapi_libs
	__timed_call __source_bashrcs
	unset -v PKGCORE_EXISTING_PATH;
}'

# Invoke this when we know that this version of pkgcore generated the env dump;
# this bypasses the safeties in loading.
alias __load_safe_environ='{
	[[ -z ${PKGCORE_TARGET_ENV} ]] && die "__load_safe_environ was invoked w/out PKGCORE_TARGET_ENV set";
	[[ -z ${T} ]] && die "__load_safe_environ requires \$T to be set";
	PKGCORE_EXISTING_PATH=${PATH};
	if [[ -n ${PKGCORE_PERF_DEBUG} ]]; then
		echo "timing source ${PKGCORE_TARGET_ENV}" >&2
		time source "${PKGCORE_TARGET_ENV}" >&2
		echo "timed source ${PKGCORE_TARGET_ENV}" >&2
	else
		source "${PKGCORE_TARGET_ENV}" >&2
	fi
	[[ $? == 0 ]] || die "sourcing saved env failed";
	__ensure_PATH "${PKGCORE_EXISTING_PATH}";
	__timed_call __load_eapi_libs
	__timed_call __source_bashrcs
	unset -v PKGCORE_EXISTING_PATH;
}'

alias __init_environ='{
	PKGCORE_EXISTING_PATH=${PATH};
	__timed_call __load_eapi_libs
	if [[ -n ${PKGCORE_PERF_DEBUG} ]]; then
		echo "timing eval \$(__generate_initial_ebuild_environ)" >&2
		time eval "$(__timed_call __generate_initial_ebuild_environ)" >&2
		echo "timed eval \$(__generate_initial_ebuild_environ)" >&2
	else
		eval "$(__generate_initial_ebuild_environ)"
	fi
	[[ $? == 0 ]] || die "failed loading initialized environment";
	__ensure_PATH "${PKGCORE_EXISTING_PATH}";
	__timed_call __source_bashrcs
	unset -v PKGCORE_EXISTING_PATH;
}'

shopt -s extdebug &> /dev/null

# if no perms are specified, dirs/files will have decent defaults
# (not secretive, but not stupid)
umask 022

# the sandbox is disabled by default except when overridden in the relevant stages
export SANDBOX_ON=0

# Used to track if we're subshelled w/in the main ebd instance, or if we're in
# a literal child process.
PKGCORE_IS_NOT_HELPER=1

# ensure the passed in PATH has its components in $PATH and that they aren't
# overridden by new entries
__ensure_PATH() {
	local existing_path=$1
	local adds
	# note this isolates the adds in the same order they appear in
	# the passed in path, maintaining that order.
	if [[ ${existing_path} != ${PATH} ]]; then
		local IFS=:
		local p
		for p in ${existing_path}; do
			# keep in mind PATH=":foon" is a valid way to say "cwd"
			[[ -z ${p} ]] && continue
			if ! __safe_has "${p}" ${PATH} && ! __safe_has "${p}" ${adds}; then
				adds=${adds:+${adds}:}${p}
			fi
		done
		[[ -n ${adds} ]] && PATH=${adds}${PATH:+:${PATH}}
	fi
	export PATH
}

__load_eapi_libs() {
	# reload depend; while it may've been loaded already, reload it so that callers can
	# rely on this setting the env up as necessary
	# finally, update the filters with functionality loaded from here-
	# always, always, *always* use our own functionality
	source "${PKGCORE_EBD_PATH}"/eapi/common.bash \
		|| die "failed sourcing eapi/common.bash"

	# load global scope EAPI functions
	source "${PKGCORE_EBD_PATH}"/.generated/libs/${EAPI}/global \
		|| die "failed sourcing EAPI ${EAPI} global scope lib"
}

# do all profile, bashrc's, and ebuild sourcing. Should only be called in setup phase, unless the
# env is *completely* missing, as it is occasionally for ebuilds during prerm/postrm.
__generate_initial_ebuild_environ() {
	local ORIG_CC=${CC}
	local ORIG_CXX=${CXX}
	local PKGCORE_EXISTING_PATH=${PATH}
	local T=${T}

	if [[ ${EBUILD_PHASE} == "setup" ]]; then
		# we specifically save the env so it's not stomped on by sourcing.
		# bug 51552
		__timed_call __environ_save_to_file "${T}"/.temp_env

		# restore the saved env vars.
		PKGCORE_SUPPRESS_BASHRCS=true
		PKGCORE_TARGET_ENV=${T}/.temp_env
		if ! __load_environ; then
			# this shouldn't happen.
			die "failed to load '${T}/.temp_env' -- fs is readonly?"
		fi
		unset -v PKGCORE_SUPPRESS_BASHRCS

		rm "${T}"/.temp_env
	fi

	[[ -n ${EBUILD} ]] && __timed_call __load_ebuild "${EBUILD}"

	if [[ ${EBUILD_PHASE} != "depend" ]]; then
		RESTRICT=${PKGCORE_FINALIZED_RESTRICT}
		unset -v PKGCORE_FINALIZED_RESTRICT
		unset -v CC CXX
		[[ -n ${ORIG_CC} ]] && export CC=${ORIG_CC}
		[[ -n ${ORIG_CXX} ]] && export CXX=${ORIG_CXX}
		unset -v ORIG_CC ORIG_CXX
	fi

	__ensure_PATH "${PKGCORE_EXISTING_PATH}"
	if [[ -n ${T} && ${EBUILD_PHASE} != "pretend" ]]; then
		# Use a file if possible; faster since bash does this lovely byte by
		# byte reading if it's a pipe. Having the file around is useful for
		# debugging also.
		__timed_call __environ_save_to_file "${T}"/.initial_environ || die "failed dumping env to '${T}/.initial_environ'"
		echo "source \"${T}\"/.initial_environ"
	else
		__timed_call __environ_dump || die "failed dumping env"
	fi
}

# Set up the bash version compatibility level. This does not disable features
# when running with a newer version, but makes it so that when bash changes
# behavior in an incompatible way, the older behavior is used instead.
__export_bash_compat() {
	[[ -z ${PKGCORE_BASH_COMPAT} ]] && die "PKGCORE_BASH_COMPAT isn't set!"

	# Set compat level only for the ebuild environment, this won't affect
	# external shell scripts.
	__var_push -n BASH_COMPAT=${PKGCORE_BASH_COMPAT}

	# BASH_COMPAT was introduced in bash-4.3, for older versions a compat
	# option must be used.
	if [[ ${PKGCORE_BASH_COMPAT} == "3.2" && ${BASH_VERSINFO[0]} -gt 3 ]]; then
		__shopt_push -s compat32
	fi

	# Explicitly set shell option (it's automatically enabled by setting
	# BASH_COMPAT) so it gets properly disabled once leaving scope. Otherwise,
	# __qa_invoke() can throw warnings when the compat42 option enabled
	# internally by bash bleeds out of scope which seems to be caused when
	# ebuilds or eclasses alter shopt options.
	[[ ${PKGCORE_BASH_COMPAT} == "4.2" ]] && __shopt_push -s compat42
}

__load_ebuild() {
	local EBUILD=$1
	[[ -f ${EBUILD} ]] || die "nonexistent ebuild: '${EBUILD}'"
	shift

	SANDBOX_ON=1
	export S=${WORKDIR}/${P}

	unset -v IUSE   REQUIRED_USE   DEPEND   RDEPEND   PDEPEND   BDEPEND   IDEPEND
	local  E_IUSE E_REQUIRED_USE E_DEPEND E_RDEPEND E_PDEPEND E_BDEPEND E_IDEPEND
	if ${PKGCORE_ACCUMULATE_PROPERTIES_RESTRICT}; then
		unset -v PROPERTIES   RESTRICT
		local  E_PROPERTIES E_RESTRICT
	fi

	__env_push
	__export_bash_compat

	# EAPI 6 and up raise expansion errors on failed globbing in global scope.
	${PKGCORE_GLOBAL_FAILGLOB} && __shopt_push -s failglob

	__qa_invoke source "${EBUILD}"
	if [[ $? != 0 ]]; then
		# rerun source in a subshell to capture stderr
		local error_msg="error sourcing ebuild"
		local source_err=$(__qa_invoke source "${EBUILD}" 2>&1)
		[[ -n ${source_err} ]] && error_msg+="\n\n${source_err}"
		die "${error_msg}"
	fi

	__env_pop

	# a reasonable default for $S
	if [[ -z ${S} ]]; then
		export S=${WORKDIR}/${P}
	fi

	# Note that this is not the same as `export RDEPEND=${RDEPEND:-${DEPEND}}`
	# That will test for unset *or* NULL (""), we want just to set if unset.
	if __safe_has "${EAPI}" 0 1 2 3; then
		if [[ ${RDEPEND-unset} == "unset" ]]; then
			export RDEPEND=${DEPEND}
		fi
	fi

	# add in dependency info from eclasses
	IUSE+=${IUSE:+ }${E_IUSE}
	REQUIRED_USE+=${REQUIRED_USE:+ }${E_REQUIRED_USE}
	DEPEND+=${DEPEND:+ }${E_DEPEND}
	RDEPEND+=${RDEPEND:+ }${E_RDEPEND}
	PDEPEND+=${PDEPEND:+ }${E_PDEPEND}
	BDEPEND+=${BDEPEND:+ }${E_BDEPEND}
	IDEPEND+=${IDEPEND:+ }${E_IDEPEND}
	if ${PKGCORE_ACCUMULATE_PROPERTIES_RESTRICT}; then
		PROPERTIES+=${PROPERTIES:+ }${E_PROPERTIES}
		RESTRICT+=${RESTRICT:+ }${E_RESTRICT}
	fi
}

# short version. think these should be sourced via at the daemon's choice, rather then defacto.
# note that exit-handling loads the die functions, thus the custom failure there.
source "${PKGCORE_EBD_PATH}"/exit-handling.bash >&2 || { echo "ERROR: failed sourcing exit-handling.bash"; exit -1; }
source "${PKGCORE_EBD_PATH}"/ebuild-default-functions.bash >&2 || die "failed sourcing ebuild-default-functions.bash"
source "${PKGCORE_EBD_PATH}"/ebuild-env-utils.bash >&2 || die "failed sourcing ebuild-env-utils.bash"

__run_ebuild_phase() {
	[[ ${PKGCORE_DEBUG} -ge 2 ]] && set -x

	# some users have $TMP/$TMPDIR to a custom dir in their home ...
	# this will cause sandbox errors with some ./configure
	# scripts, so set it to $T.
	local -x TMP=${T}
	local -x TMPDIR=${T}

	__env_push
	__export_bash_compat
	${PKGCORE_EBUILD_PHASE_FUNC} && __var_push -n EBUILD_PHASE_FUNC=$1

	# die when encountering unknown commands
	command_not_found_handle() {
		local msg="${EBUILD_PHASE_FUNC}(): unknown command '$1'"
		[[ $# -gt 1 ]] && msg+=" when executing: '$*'"
		if ${PKGCORE_NONFATAL}; then
			eerror "${msg}"
			return 1
		fi
		die "${msg}"
	}

	# load phase scope EAPI functions
	source "${PKGCORE_EBD_PATH}"/.generated/libs/${EAPI}/$1 \
		|| die "failed sourcing EAPI ${EAPI} $1 phase scope lib"

	cd "${PKGCORE_EMPTYDIR}" || die "unable to cd into ${PKGCORE_EMPTYDIR}"
	__qa_run_function_if_exists __phase_pre_$1
	__qa_run_function_if_exists pre_$1

	if __is_function __dyn_$1; then
		__dyn_$1
	elif __is_function $1; then
		__qa_invoke $1
	else
		__qa_run_function_if_exists __phase_$1
	fi

	__qa_run_function_if_exists post_$1
	__qa_run_function_if_exists __phase_post_$1

	__env_pop

	# don't leak func to exported env
	unset -f command_not_found_handle

	[[ ${PKGCORE_DEBUG} -lt 4 ]] && set +x
}

# general func to call for phase execution. this handles necessary env
# loading/dumping, and executing pre/post/dyn calls.
__execute_phases() {
	local PKGCORE_DIE_OUTPUT_DETAILS PKGCORE_SUPPRESS_BASHRCS
	local PKGCORE_SAVE_ENV PKGCORE_TARGET_ENV PKGCORE_MUST_EXPORT_ENV=false

	# give us pretty tracebacks.
	shopt -s extdebug

	trap "exit 2" SIGINT
	trap "exit 9" SIGQUIT
	trap "exit 1" SIGTERM
	declare -rx PKGCORE_EBUILD_PROCESS_PID=${BASHPID}

	local ret
	for EBUILD_PHASE in $*; do
		PKGCORE_SAVE_ENV=true
		PKGCORE_DIE_OUTPUT_DETAILS=true
		PKGCORE_SUPPRESS_BASHRCS=false

		case ${EBUILD_PHASE} in
			nofetch|pretend)
				PKGCORE_SUPPRESS_BASHRCS=true
				__init_environ

				PKGCORE_DIE_OUTPUT_DETAILS=false
				__run_ebuild_phase pkg_${EBUILD_PHASE}
				PKGCORE_SAVE_ENV=false
				ret=0
				;;
			prerm|postrm|preinst|postinst|config)
				[[ ${EBUILD_PHASE} == postrm ]] && PKGCORE_SAVE_ENV=false
				export SANDBOX_ON=0

				PKGCORE_TARGET_ENV=${T}/environment
				__load_environ || die "failed loading env during ${EBUILD_PHASE} phase"

				__run_ebuild_phase pkg_${EBUILD_PHASE}
				ret=0
				;;
			unpack|prepare|configure|compile|test|install)
				if [[ ${SANDBOX_DISABLED=0} == 0 ]]; then
					export SANDBOX_ON=1
				else
					export SANDBOX_ON=0
				fi

				[[ ${PKGCORE_DEBUG} -ge 3 ]] && set -x
				PKGCORE_TARGET_ENV=${T}/environment
				__load_safe_environ || die "failed loading env during ${EBUILD_PHASE} phase"
				[[ -z ${S} ]] && die "\$S was null, path=${PATH}"

				__run_ebuild_phase src_${EBUILD_PHASE}
				ret=0
				;;
			setup|setup-binpkg)
				EBUILD_PHASE="setup"

				# binpkgs don't need to reinitialize the env.
				if [[ ${EBUILD_PHASE} == "setup" ]]; then
					[[ -n ${DISTCC_LOG} ]] && addwrite "$(dirname ${DISTCC_LOG})"

					if __feature_is_enabled ccache; then
						export CCACHE_DIR
						[[ -n ${CCACHE_SIZE} ]] && ccache -M ${CCACHE_SIZE} &> /dev/null
					fi

					[[ ${PKGCORE_DEBUG} -ge 2 ]] && set -x
					__init_environ
				else
					PKGCORE_TARGET_ENV=${T}/environment
					__load_environ || die "failed loading env during ${EBUILD_PHASE} phase"
				fi

				# pkg_setup needs to be run outside the sandbox for tmp file
				# creation; for example, awking and piping a file in /tmp
				# requires a temp file to be created in /etc. If pkg_setup is
				# in the sandbox, both our lilo and apache ebuilds break.
				export SANDBOX_ON=0

				__run_ebuild_phase pkg_${EBUILD_PHASE}
				ret=0;
				;;
			depend|generate_env)
				SANDBOX_ON=1
				PKGCORE_SAVE_ENV=false

				PKGCORE_DIE_OUTPUT_DETAILS=false

				__timed_call __load_eapi_libs
				__load_ebuild "${EBUILD}"

				if [[ ${EBUILD_PHASE} == depend ]]; then
					__dump_metadata_keys
				else
					# Use gawk if at possible; it's a fair bit faster since
					# bash likes to do byte by byte reading.
					local __path
					__path=$(PATH=/usr/bin:/bin type -P gawk)
					if [[ $? == 0 ]]; then
						{ unset -v __path; __environ_dump; } | \
							LC_ALL=C "${__path}" -F $'\0' 'BEGIN { content="";chars=0;RS="\0";ORS=""} {chars += length($0);content = content $0} END {printf("receive_env %i\n%s",chars, content)}' >&${PKGCORE_EBD_WRITE_FD}
					else
						local my_env=$(__environ_dump)
						__ebd_write_line "receive_env ${#my_env}"
						__ebd_write_raw "${my_env}"
						unset -v my_env __path
					fi
				fi
				;;
			*)
				die "invalid command: ${EBUILD_PHASE}"
				;;
		esac

		${PKGCORE_SAVE_ENV} && PKGCORE_MUST_EXPORT_ENV=true
		[[ ${PKGCORE_DEBUG} -lt 4 ]] && set +x
	done

	if ${PKGCORE_MUST_EXPORT_ENV}; then
		__timed_call __environ_save_to_file "${T}"/environment
	fi
	return ${ret:-0}
}

__dump_metadata_keys() {
	# note this function does /not/ use shopt pushing/popping; it should only
	# be invoked after ebuild code has done it's thing, as such we no longer care,
	# and directly screw w/ it for speed reasons- about 5% speedup in metadata regen.
	set -f
	local key phases phase
	for key in "${PKGCORE_METADATA_KEYS[@]}"; do
		if [[ ${key} == DEFINED_PHASES ]]; then
			for phase in "${PKGCORE_EBUILD_PHASES[@]}"; do
				__is_function "${phase}" && phases+=( ${phase} )
			done
			__ebd_write_line "key DEFINED_PHASES=${phases[@]:--}"
		else
			# deref the val, if it's not empty/unset, then spit a key command to EBD
			# after using echo to normalize whitespace (specifically removal of newlines)
			if [[ ${!key:-unset} != "unset" ]]; then
				# note that we explicitly bypass the normal functions, and directly
				# write to the FD. This is done since it's about 25% faster for our usage;
				# if we used the functions, we'd have to subshell the 'echo ${!key}', which
				# because of bash behaviour, means the content would be read byte by byte.
				echo -n "key ${key}=" >&${PKGCORE_EBD_WRITE_FD}
				echo ${!key} >&${PKGCORE_EBD_WRITE_FD}
			fi
		fi
	done
	set +f
}

set +f

export XARGS
set +H -h
:
