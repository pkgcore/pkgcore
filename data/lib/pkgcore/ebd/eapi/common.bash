# Common EAPI functionality (mainly phase related)

# debug-print() gets called from many places with verbose status information useful
# for tracking down problems. The output is in ${T}/eclass-debug.log.
# You can set ECLASS_DEBUG_OUTPUT to redirect the output somewhere else as well.
# The special "on" setting echoes the information, mixing it with the rest of the
# emerge output.
# You can override the setting by exporting a new one from the console, or you can
# set a new default in make.*. Here the default is "" or unset.

# in the future might use e* from /etc/init.d/functions.sh if i feel like it
debug-print() {
	if __safe_has ${EBUILD_PHASE} depend nofetch pretend config info postinst; then
		return
	fi
	# if ${T} isn't defined, we're in dep calculation mode and
	# shouldn't do anything
	[[ -z ${T} ]] && return 0

	local _item
	for _item in "$@"; do
		# extra user-configurable targets
		if [[ ${ECLASS_DEBUG_OUTPUT} == "on" ]]; then
			echo "debug: ${_item}"
		elif [[ -n ${ECLASS_DEBUG_OUTPUT} ]]; then
			echo "debug: ${_item}" >> "${ECLASS_DEBUG_OUTPUT}"
		fi

		# default target
		echo "${_item}" >> "${T}"/eclass-debug.log
		chmod g+w "${T}"/eclass-debug.log &> /dev/null
	done
	# let the portage user own/write to this file
}

# The following 2 functions are debug-print() wrappers

debug-print-function() {
	local str="$1: entering function"
	shift
	debug-print "${str}, parameters: $*"
}

debug-print-section() {
	debug-print "now in section $*"
}

__get_libdir() {
	local libdir=$1 libdir_var="LIBDIR_${ABI}"
	[[ -n ${ABI} && -n ${!libdir_var} ]] && libdir=${!libdir_var}
	echo "${libdir}"
}

__phase_pre_phase() {
	if [[ -d ${S} ]]; then
		cd "${S}"
	elif __safe_has "${EAPI}" 0 1 2 3; then
		cd "${WORKDIR}"
	elif [[ -n ${A} ]]; then
		die "source directory '${S}' doesn't exist, but \${A} isn't empty (see S-WORKDIR-FALLBACK in PMS)"
	else
		local phase
		# eapi4 blatant idiocy...
		for phase in unpack prepare configure compile test install; do
			[[ ${phase} == ${EBUILD_PHASE} ]] && break
			__is_function src_${phase} || continue
			# to reach here means that (for example), we're doing src_install, and src_compile was defined
			# but S doesn't exist.
			die "source directory '${S}' doesn't exist, \${A} is defined, and there was a defined " \
				"phase function '${phase}' prior to '${EBUILD_PHASE}'; please see S-WORKDIR-FALLBACK " \
				"in pms for the details of what is allowed for eapi4 and later"
		done
		cd "${WORKDIR}"
	fi
}

__phase_pre_src_unpack()  { cd "${WORKDIR}"; }
__phase_pre_src_prepare() { __phase_pre_phase; }
__phase_pre_src_test()    { __phase_pre_phase; }

__phase_pre_src_configure() {
	local var
	for var in C{BUILD,HOST,TARGET,C,XX} {AS,LD,{,LIB}C{,XX}}FLAGS CCACHE_DIR; do
		[[ -n ${!var+set} ]] && export ${var}="${!var}"
	done
	__phase_pre_phase
}

__phase_pre_src_compile() {
	# just reuse the default_pre_src_configure; this means we don't have to care
	# if the eapi has configure or not.
	__phase_pre_src_configure

	if __feature_is_enabled distcc; then
		[[ -n ${DISTCC_DIR} ]] && addwrite "${DISTCC_DIR}"
		if __feature_is_enabled distcc-pump; then
			eval $(pump --startup) || echo "Warning: Failed starting pump" >&2
			trap 'pump --shutdown' EXIT
		fi
	fi
}

__phase_post_src_compile() {
	if __feature_is_enabled distcc && __feature_is_enabled distcc-pump; then
		pump --shutdown
		trap - EXIT
	fi
}

__phase_pre_src_install() {
	export PKGCORE_DESTTREE=/usr PKGCORE_INSDESTTREE='' \
		PKGCORE_EXEDESTTREE='' PKGCORE_DOCDESTTREE=''
	if ${PKGCORE_HAS_DESTTREE}; then
		export DESTTREE=${PKGCORE_DESTTREE}
		export INSDESTTREE=${PKGCORE_INSDESTTREE}
	fi
	export INSOPTIONS="-m0644" EXEOPTIONS="-m0755"
	export LIBOPTIONS="-m0644" DIROPTIONS="-m0755"
	export PORTAGE_COMPRESS=${PORTAGE_COMPRESS:-bzip2}
	export PORTAGE_COMPRESS_FLAGS=${PORTAGE_COMPRESS_FLAGS:--9}
	export D
	rm -rf "${D}"
	if ${PKGCORE_PREFIX_SUPPORT}; then
		[[ -n ${ED+set} ]] || \
			die "variable ED is unset, but prefix mode is enabled, internal error?"
		export ED=${ED}
		mkdir -p "${ED}"
	else
		mkdir "${D}"
	fi
	__phase_pre_phase
}

# Iterate over the inherited EAPI stack running all EAPI specific functions
# starting with a defined prefix. Defaults to running in inherited order from
# the current package's EAPI to the oldest inherited EAPI. To run in overriding
# order (the reverse direction), pass '--override' as the first argument.
__run_eapi_funcs() {
	local eapis=( ${PKGCORE_EAPI_INHERITS} )
	if [[ $1 == --override ]]; then
		eapis=( $(__reverse_array eapis) )
		shift
	fi
	local func_prefix=$1
	shift

	local eapi
	for eapi in "${eapis[@]}"; do
		__qa_run_function_if_exists ${func_prefix}_eapi${eapi} "$@"
	done
}

:
