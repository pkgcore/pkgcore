# default functions for ebuild env that aren't saved- specific to the portage instance.

# sandbox support functions
addread() {
	export SANDBOX_READ=${SANDBOX_READ}:$1
}

addwrite() {
	export SANDBOX_WRITE=${SANDBOX_WRITE}:$1
}

adddeny() {
	export SANDBOX_DENY=${SANDBOX_DENY}:$1
}

addpredict() {
	export SANDBOX_PREDICT=${SANDBOX_PREDICT}:$1
}

__dyn_src_install() {
	if __is_function src_install; then
		__qa_invoke src_install
	else
		__qa_run_function_if_exists __phase_src_install
	fi

	"${PKGCORE_EBD_PATH}"/helpers/internals/prepall
	${PKGCORE_PREFIX_SUPPORT} || local ED=${D}
	cd "${ED}"

	if type -p scanelf > /dev/null; then
		# Make sure we disallow insecure RUNPATH/RPATH's
		# Don't want paths that point to the tree where the package was built
		# (older, broken libtools would do this).  Also check for null paths
		# because the loader will search $PWD when it finds null paths.
		local f=$(scanelf -qyRF '%r %p' "${ED}" | grep -E "(${WORKDIR}|${ED}|: |::|^ )")
		if [[ -n ${f} ]]; then
			echo -ne '\a\n'
			echo "QA Notice: the following files contain insecure RUNPATH's"
			echo " Please file a bug about this at http://bugs.gentoo.org/"
			echo " For more information on this issue, kindly review:"
			echo " http://bugs.gentoo.org/81745"
			echo "${f}"
			echo -ne '\a\n'
			__feature_is_enabled stricter && die "Insecure binaries detected"
			echo "autofixing rpath..."
			TMPDIR=${WORKDIR} scanelf -BXr ${f} -o /dev/null
		fi

		# Check for setid binaries but are not built with BIND_NOW
		f=$(scanelf -qyRF '%b %p' "${ED}")
		if [[ -n ${f} ]]; then
			echo -ne '\a\n'
			echo "QA Notice: the following files are setXid, dyn linked, and using lazy bindings"
			echo " This combination is generally discouraged.  Try forcing via bashrc"
			echo " LDFLAGS='-Wl,-z,now' for the pkg, or disable FEATURES=stricter"
			echo "${f}"
			echo -ne '\a\n'
			__feature_is_enabled stricter && die "Aborting due to lazy bindings"
			sleep 1
		fi

		# TEXTREL's are baaaaaaaad
		f=$(scanelf -qyRF '%t %p' "${ED}")
		if [[ -n ${f} ]]; then
			echo -ne '\a\n'
			echo "QA Notice: the following files contain runtime text relocations"
			echo " Text relocations require a lot of extra work to be preformed by the"
			echo " dynamic linker which will cause serious performance impact on IA-32"
			echo " and might not function properly on other architectures hppa for example."
			echo " If you are a programmer please take a closer look at this package and"
			echo " consider writing a patch which addresses this problem."
			echo "${f}"
			echo -ne '\a\n'
			__feature_is_enabled stricter && die "Aborting due to textrels"
			sleep 1
		fi

		# Check for files with executable stacks
		f=$(scanelf -qyRF '%e %p' "${ED}")
		if [[ -n ${f} ]]; then
			echo -ne '\a\n'
			echo "QA Notice: the following files contain executable stacks"
			echo " Files with executable stacks will not work properly (or at all!)"
			echo " on some architectures/operating systems.  A bug should be filed"
			echo " at http://bugs.gentoo.org/ to make sure the file is fixed."
			echo "${f}"
			echo -ne '\a\n'
			__feature_is_enabled stricter && die "Aborting due to +x stack"
			sleep 1
		fi

		# Create NEEDED and NEEDED.ELF.2 files required for things like preserve-libs
		# TODO: someday find a way to move this to the triggers implementation to allow
		# for parallelization of the scanning- if useful.
		scanelf -qyRF '%a;%p;%S;%r;%n' "${ED}" | { while IFS= read -r l; do
			arch=${l%%;*}; l=${l#*;}
			obj="/${l%%;*}"; l=${l#*;}
			soname=${l%%;*}; l=${l#*;}
			rpath=${l%%;*}; l=${l#*;}; [[ ${rpath} == "  -  " ]] && rpath=""
			needed=${l%%;*}; l=${l#*;}
			echo "${obj} ${needed}" >> "${T}"/NEEDED
			echo "${arch:3};${obj};${soname};${rpath};${needed}" >> "${T}"/NEEDED.ELF.2
		done }
	fi
}

__dyn_pkg_preinst() {
	if __is_function pkg_preinst; then
		__qa_invoke pkg_preinst
	else
		__qa_run_function_if_exists __phase_pkg_preinst
	fi

	${PKGCORE_PREFIX_SUPPORT} || local ED=${D}

	# total suid control.
	if __feature_is_enabled suidctl > /dev/null; then
		sfconf=/etc/portage/suidctl.conf
		echo ">>> Performing suid scan in ${ED}"
		local i
		for i in $(find "${ED}" -type f \( -perm -4000 -o -perm -2000 \) ); do
			if [[ -s ${sfconf} ]]; then
				suid=$(grep ^${i/${ED}/}$ "${sfconf}")
				if [[ ${suid} == ${i/${ED}/} ]]; then
					echo "- ${i/${ED}/} is an approved suid file"
				else
					echo ">>> Removing sbit on non registered ${i/${ED}/}"
					chmod ugo-s "${i}"
					grep ^#${i/${ED}/}$ ${sfconf} > /dev/null || {
						# sandbox prevents us from writing directly
						# to files outside of the sandbox, but this
						# can easly be bypassed using the addwrite() function
						addwrite "${sfconf}"
						echo ">>> Appending commented out entry to ${sfconf} for ${PF}"
						ls_ret=$(ls -ldh "${i}")
						echo "## ${ls_ret%${ED}*}${ls_ret#*${ED}}" >> "${sfconf}"
						echo "#${i/${ED}/}" >> "${sfconf}"
						# no delwrite() eh?
						# delwrite ${sconf}
					}
				fi
			else
				echo "suidctl feature set but you are lacking a ${sfconf}"
			fi
		done
	fi

	# SELinux file labeling (needs to always be last in dyn_preinst)
	if __feature_is_enabled selinux; then
		# only attempt to label if setfiles is executable
		# and 'context' is available on selinuxfs.
		if [[ -f /selinux/context && -x /usr/sbin/setfiles ]]; then
			echo ">>> Setting SELinux security labels"
			if [[ -f ${POLICYDIR}/file_contexts/file_contexts ]]; then
				cp -f "${POLICYDIR}"/file_contexts/file_contexts "${T}"
			else
				make -C "${POLICYDIR}" FC=${T}/file_contexts "${T}"/file_contexts
			fi

			addwrite /selinux/context
			/usr/sbin/setfiles -r "${ED}" "${T}"/file_contexts "${ED}" \
				|| die "failed to set SELinux security labels"
		else
			# nonfatal, since merging can happen outside a SE kernel
			# like during a recovery situation
			echo "!!! Unable to set SELinux security labels"
		fi
	fi
}

inherit() {
	[[ -z $@ ]] && die "${FUNCNAME}: missing eclass argument"
	local INHERIT_DEPTH=$(( ${INHERIT_DEPTH-0} + 1 ))

	if [[ ${INHERIT_DEPTH} -gt 1 ]]; then
		debug-print "*** Multiple Inheritance (level: ${INHERIT_DEPTH})"
	fi

	local location olocation
	local ECLASS

	# note that this ensures any later unsets/mangling, the ebuilds original
	# setting is protected.
	local IUSE REQUIRED_USE DEPEND RDEPEND PDEPEND BDEPEND IDEPEND
	if ${PKGCORE_ACCUMULATE_PROPERTIES_RESTRICT}; then
		local PROPERTIES RESTRICT
	fi

	# keep track of direct ebuild inherits
	[[ ${INHERIT_DEPTH} -eq 1 ]] && INHERIT+=" $@"

	for ECLASS in "$@"; do
		if [[ ${EBUILD_PHASE} != "depend" ]]; then
			if ! __safe_has "${ECLASS}" ${INHERITED}; then
				echo
				echo "QA Notice: ECLASS '${ECLASS}' illegal conditional inherit in ${CATEGORY}/${PF}" >&2
				echo
			fi
		fi

		unset -v IUSE REQUIRED_USE DEPEND RDEPEND PDEPEND BDEPEND IDEPEND
		if ${PKGCORE_ACCUMULATE_PROPERTIES_RESTRICT}; then
			unset -v PROPERTIES RESTRICT
		fi

		__internal_inherit "$1" || die "${FUNCNAME}: failed sourcing $1"

		# If each var has a value, append it to the global variable E_* to
		# be applied after everything is finished. New incremental behavior.
		[[ -n ${IUSE}         ]] && E_IUSE+=${E_IUSE:+ }${IUSE}
		[[ -n ${REQUIRED_USE} ]] && E_REQUIRED_USE+=${E_REQUIRED_USE:+ }${REQUIRED_USE}
		[[ -n ${DEPEND}       ]] && E_DEPEND+=${E_DEPEND:+ }${DEPEND}
		[[ -n ${RDEPEND}      ]] && E_RDEPEND+=${E_RDEPEND:+ }${RDEPEND}
		[[ -n ${PDEPEND}      ]] && E_PDEPEND+=${E_PDEPEND:+ }${PDEPEND}
		[[ -n ${BDEPEND}      ]] && E_BDEPEND+=${E_BDEPEND:+ }${BDEPEND}
		[[ -n ${IDEPEND}      ]] && E_IDEPEND+=${E_IDEPEND:+ }${IDEPEND}
		if ${PKGCORE_ACCUMULATE_PROPERTIES_RESTRICT}; then
			[[ -n ${PROPERTIES} ]] && E_PROPERTIES+=${E_PROPERTIES:+ }${PROPERTIES}
			[[ -n ${RESTRICT}   ]] && E_RESTRICT+=${E_RESTRICT:+ }${RESTRICT}
		fi

		# while other PMs have checks to keep this unique, we don't; no need,
		# further up the stack (python side) we uniquify this.
		# if you try to do it in bash rather than python, it's ~10% slower regen
		INHERITED+=" ${ECLASS}"

		shift
	done
}

# Exports stub functions that call the eclass's functions, thereby making them default.
# For example, if ECLASS="base" and you call "EXPORT_FUNCTIONS src_unpack", the following
# code will be eval'd:
# src_unpack() { base_src_unpack; }
EXPORT_FUNCTIONS() {
	if [[ -z ${ECLASS} ]]; then
		die "EXPORT_FUNCTIONS without a defined ECLASS"
	fi
	local phase_func
	for phase_func in $*; do
		debug-print "EXPORT_FUNCTIONS: ${phase_func} -> ${ECLASS}_${phase_func}"
		eval "${phase_func}() { ${ECLASS}_${phase_func} "\$@" ; }" > /dev/null
	done
}

:
