# Install destination commands

into() {
	${PKGCORE_PREFIX_SUPPORT} || local ED=${D}
	if [[ $1 == "/" ]]; then
		export PKGCORE_DESTTREE=""
	else
		export PKGCORE_DESTTREE=$1
	fi

	# only EAPI <= 6 supports DESTTREE
	${PKGCORE_HAS_DESTTREE} && export DESTTREE=${PKGCORE_DESTTREE}
}

insinto() {
	${PKGCORE_PREFIX_SUPPORT} || local ED=${D}
	if [[ $1 == "/" ]]; then
		export PKGCORE_INSDESTTREE=""
	else
		export PKGCORE_INSDESTTREE=$1
	fi

	# only EAPI <= 6 supports INSDESTTREE
	${PKGCORE_HAS_DESTTREE} && export INSDESTTREE=${PKGCORE_INSDESTTREE}
}

exeinto() {
	${PKGCORE_PREFIX_SUPPORT} || local ED=${D}
	if [[ $1 == "/" ]]; then
		export PKGCORE_EXEDESTTREE=""
	else
		export PKGCORE_EXEDESTTREE=$1
	fi
}

docinto() {
	${PKGCORE_PREFIX_SUPPORT} || local ED=${D}
	if [[ $1 == "/" ]]; then
		export PKGCORE_DOCDESTTREE=""
	else
		export PKGCORE_DOCDESTTREE=$1
	fi
}

# Install options commands

insopts() {
	{ has -s "$@" || has --strip "$@"; } && \
		ewarn "insopts shouldn't be given -s; stripping should be left to the manager."
	export INSOPTIONS=$@
}

diropts() {
	export DIROPTIONS=$@
}

exeopts() {
	{ has -s "$@" || has --strip "$@"; } && \
		ewarn "exeopts shouldn't be given -s; stripping should be left to the manager."
	export EXEOPTIONS=$@
}

libopts() {
	{ has -s "$@" || has --strip "$@"; } && \
		ewarn "libopts shouldn't be given -s; stripping should be left to the manager."
	export LIBOPTIONS=$@
}

# Install command

einstall() {
	${PKGCORE_PREFIX_SUPPORT} || local ED=${D}
	# CONF_PREFIX is only set if they didn't pass in libdir above
	local LOCAL_EXTRA_EINSTALL=( ${EXTRA_EINSTALL} )
	local CONF_LIBDIR=$(__get_libdir)
	if [[ -n ${CONF_LIBDIR} && ${CONF_PREFIX:-unset} != "unset" ]]; then
		local EI_DESTLIBDIR=${ED%%/}/${CONF_PREFIX%%/}/${CONF_LIBDIR%%/}/
		LOCAL_EXTRA_EINSTALL+=( libdir=${EI_DESTLIBDIR} )
		unset -v EI_DESTLIBDIR
	fi

	if ! [[ -f Makefile || -f GNUmakefile || -f makefile ]]; then
		die "no Makefile found"
	fi

	# Reset IFS for LOCAL_EXTRA_EINSTALL, should users be up to something.
	local IFS=$' \t\n'
	set -- \
		${MAKE:-make} \
		prefix="${ED}/usr" \
		datadir="${ED}/usr/share" \
		infodir="${ED}/usr/share/info" \
		localstatedir="${ED}/var/lib" \
		mandir="${ED}/usr/share/man" \
		sysconfdir="${ED}/etc" \
		${LOCAL_EXTRA_EINSTALL[@]} \
		"$@" install
	[[ ${PKGCORE_DEBUG} != 0 ]] && "$@" -n
	"$@" || die "einstall failed"
}
