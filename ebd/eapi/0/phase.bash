# Phase specific functions -- only defined when running ebuild phases

## Build commands

econf() {
	local ret
	ECONF_SOURCE=${ECONF_SOURCE:-.}
	if [[ ! -x ${ECONF_SOURCE}/configure ]]; then
		[[ -f ${ECONF_SOURCE}/configure ]] && die "configure script isn't executable"
		die "no configure script found"
	fi

	if [[ -d /usr/share/gnuconfig ]]; then
		local x
		find "${WORKDIR}" -type f \( -name config.guess -o -name config.sub \) | \
			while read x; do
			echo "econf: replacing ${x} with /usr/share/gnuconfig/${x##*/}"
			cp -f "/usr/share/gnuconfig/${x##*/}" "${x}"
		done
	fi

	# if the profile defines a location to install libs to aside from default, pass it on.
	# if the ebuild passes in --libdir, they're responsible for the conf_libdir fun.
	local CONF_LIBDIR=$(__get_libdir)
	if [[ -n ${CONF_LIBDIR} && $* != *"--libdir="* ]]; then
		if [[ $* == *"--exec-prefix="* ]]; then
			local args=$(echo $*)
			local -a prefix=( $(echo ${args/*--exec-prefix[= ]}) )
			CONF_PREFIX=${prefix/--*}
			[[ ${CONF_PREFIX} != /* ]] && CONF_PREFIX=/${CONF_PREFIX}
		elif [[ $* == *"--prefix="* ]]; then
			local args=$(echo $*)
			local -a pref=( $(echo ${args/*--prefix[= ]}) )
			CONF_PREFIX=${prefix/--*}
			[[ ${CONF_PREFIX} != /* ]] && CONF_PREFIX=/${CONF_PREFIX}
		else
			CONF_PREFIX=/usr
		fi
		export CONF_PREFIX
		[[ ${CONF_LIBDIR} != /* ]] && CONF_LIBDIR=/${CONF_LIBDIR}
		set -- --libdir="$(__strip_duplicate_slashes "${CONF_PREFIX}${CONF_LIBDIR}")" "$@"
	fi

	# get EAPI specific arguments
	local help_text=$("${ECONF_SOURCE}/configure" --help 2> /dev/null)
	set -- $(__run_eapi_funcs --override __econf_options "${help_text}") "$@"

	# Reset IFS since we're interpreting user supplied EXTRA_ECONF.
	local IFS=$' \t\n'
	set -- "${ECONF_SOURCE}/configure" \
		--prefix="${EPREFIX}"/usr \
		${CBUILD:+--build="${CBUILD}"} \
		--host="${CHOST}" \
		${CTARGET:+--target="${CTARGET}"} \
		--mandir="${EPREFIX}"/usr/share/man \
		--infodir="${EPREFIX}"/usr/share/info \
		--datadir="${EPREFIX}"/usr/share \
		--sysconfdir="${EPREFIX}"/etc \
		--localstatedir="${EPREFIX}"/var/lib \
		"$@" \
		${EXTRA_ECONF}

	echo "$@"

	if ! "$@"; then
		if [[ -s config.log ]]; then
			echo
			echo "!!! Please attach the config.log to your bug report:"
			echo "!!! ${PWD}/config.log"
		fi
		die "econf failed"
	fi
	return $?
}

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

## Package manager query commands

has_version() { return $(__ebd_ipc_cmd ${FUNCNAME} "" "$@"); }
best_version() { __ebd_ipc_cmd ${FUNCNAME} "" "$@"; }

## Install destination commands

into() {
	${PKGCORE_PREFIX_SUPPORT} || local ED=${D}
	if [[ $1 == "/" ]]; then
		export DESTTREE=""
	else
		export DESTTREE=$1
	fi
}

insinto() {
	${PKGCORE_PREFIX_SUPPORT} || local ED=${D}
	if [[ $1 == "/" ]]; then
		export INSDESTTREE=""
	else
		export INSDESTTREE=$1
	fi
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

## Install options commands

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

## USE flag commands

use() {
	if [[ ! ${1#!} =~ ${PKGCORE_IUSE_EFFECTIVE} ]]; then
		die "USE flag '${1#!}' not in IUSE for ${CATEGORY}/${PF}"
	fi

	# Ensure USE is split on normal IFS.
	local IFS=$' \t\n'

	if [[ ${1:0:1} == "!" ]]; then
		! __safe_has "${1#!}" ${USE}
	else
		__safe_has "$1" ${USE}
	fi
}

usev() {
	if use "$1"; then
		echo "${1#!}"
		return 0
	fi
	return 1
}

useq() {
	use "$@"
}

use_with() {
	if [[ -z $1 ]]; then
		echo "!!! use_with() called without a parameter." >&2
		echo "!!! use_with <USEFLAG> [<flagname> [value]]" >&2
		return
	fi

	local uw_suffix=""
	if __safe_has "${EAPI}" 0 1 2 3; then
		uw_suffix=${3:+=$3}
	else
		uw_suffix=${3+=$3}
	fi

	local uword=$2
	if [[ -z ${uword} ]]; then
		uword=$1
	fi

	if use "$1"; then
		echo "--with-${uword}${uw_suffix}"
		return 0
	fi
	echo "--without-${uword}"
	return 1
}

use_enable() {
	if [[ -z $1 ]]; then
		echo "!!! use_enable() called without a parameter." >&2
		echo "!!! use_enable <USEFLAG> [<flagname> [value]]" >&2
		return
	fi

	local ue_suffix=""
	if __safe_has "${EAPI}" 0 1 2 3; then
		ue_suffix=${3:+=$3}
	else
		ue_suffix=${3+=$3}
	fi

	local uword=$2
	if [[ -z ${uword} ]]; then
		uword=$1
	fi

	if use "$1"; then
		echo "--enable-${uword}${ue_suffix}"
		return 0
	fi
	echo "--disable-${uword}"
	return 1
}

## Misc commands

unpack() {
	local file file_match filename myfail srcdir taropts tar_subdir
	taropts='--no-same-owner'

	[[ $# -eq 0 ]] && die "${FUNCNAME}: missing archive arguments to extract"

	for file in "$@"; do
		echo ">>> Unpacking ${file} to ${PWD}"
		myfail="${FUNCNAME}: failure unpacking ${file}"

		if [[ ${file} != */* ]]; then
			# regular filename get prefixed with ${DISTDIR}/
			srcdir=${DISTDIR}/
		elif [[ ${file} == "./"* ]]; then
			# relative paths get passed through
			srcdir=""
		else
			srcdir=${DISTDIR}/

			if ${PKGCORE_UNPACK_ABSOLUTE_PATHS}; then
				# EAPI 6 and up allows absolute paths
				srcdir=""
				[[ ${file} == ${DISTDIR%%/}/* ]] && \
					eqawarn "QA Notice: unpack() argument contains redundant \${DISTDIR}: ${file}"
			elif [[ ${file} == ${DISTDIR%%/}/* ]]; then
				die "${FUNCNAME}: arguments must not begin with \${DISTDIR}"
			elif [[ ${file} == /* ]]; then
				die "${FUNCNAME}: arguments must not be absolute paths"
			else
				die "${FUNCNAME}: relative paths must be prefixed with './' in EAPI ${EAPI}"
			fi
		fi

		[[ ! -e ${srcdir}${file} ]] && die "${myfail}: file doesn't exist"
		[[ ! -s ${srcdir}${file} ]] && die "${myfail}: empty file"

		filename=${file##*/}

		file_match=${file}
		${PKGCORE_UNPACK_CASE_INSENSITIVE} && file_match=$(LC_ALL=C tr "[:upper:]" "[:lower:]" <<< "${file}")

		case ${file_match} in
			*.tar)
				tar xf "${srcdir}${file}" ${taropts} || die "${myfail}"
				;;
			*.tar.gz|*.tgz|*.tar.Z|*.tar.z)
				tar xf "${srcdir}${file}" -I"${PORTAGE_GZIP_COMMAND}" ${taropts} || die "${myfail}"
				;;
			*.tar.bz2|*.tbz2|*.tbz)
				tar xf "${srcdir}${file}" -I"${PORTAGE_BZIP2_COMMAND}" ${taropts} || die "${myfail}"
				;;
			*.tar.lzma)
				tar xf "${srcdir}${file}" -Ilzma ${taropts} || die "${myfail}"
				;;
			*.tar.xz)
				if __safe_has "${EAPI}" 0 1 2; then
					echo "${FUNCNAME}: *.tar.xz archives are unsupported in EAPI ${EAPI}" >&2
					continue;
				fi
				tar xf "${srcdir}${file}" -I"${PORTAGE_XZ_COMMAND}" ${taropts} || die "${myfail}"
				;;
			*.txz)
				if __safe_has "${EAPI}" 0 1 2 3 4 5; then
					echo "${FUNCNAME}: *.txz archives are unsupported in EAPI ${EAPI}" >&2
					continue;
				fi
				tar xf "${srcdir}${file}" -I"${PORTAGE_XZ_COMMAND}" ${taropts} || die "${myfail}"
				;;
			*.ZIP|*.zip|*.jar)
				{ set +x; while :; do echo n || break; done } | \
					unzip -qo "${srcdir}${file}" || die "${myfail}"
				;;
			*.gz|*.Z|*.z)
				${PORTAGE_GUNZIP_COMMAND:-${PORTAGE_GZIP_COMMAND} -d} -c "${srcdir}${file}" > ${filename%.*} || die "${myfail}"
				;;
			*.bz2|*.bz)
				${PORTAGE_BUNZIP2_COMMAND:-${PORTAGE_BZIP2_COMMAND} -d} -c "${srcdir}${file}" > ${filename%.*} || die "${myfail}"
				;;
			*.xz)
				if __safe_has "${EAPI}" 0 1 2; then
					echo "${FUNCNAME}: *.xz archives are unsupported in EAPI ${EAPI}" >&2
					continue;
				fi
				${PORTAGE_UNXZ_COMMAND:-${PORTAGE_XZ_COMMAND} -d} < "${srcdir}${file}" > ${filename%.*} || die "${myfail}"
				;;
			*.7Z|*.7z)
				local my_output
				my_output=$(7z x -y "${srcdir}${file}")
				if [[ $? -ne 0 ]]; then
					echo "${my_output}" >&2
					die "${myfail}"
				fi
				;;
			*.RAR|*.rar)
				unrar x -idq -o+ "${srcdir}${file}" || die "${myfail}"
				;;
			*.LHa|*.LHA|*.lha|*.lzh)
				lha xfq "${srcdir}${file}" || die "${myfail}"
				;;
			*.a|*.deb)
				ar x "${srcdir}${file}" || die "${myfail}"
				;;
			*.lzma)
				lzma -dc "${srcdir}${file}" > ${filename%.*} || die "${myfail}"
				;;
			*)
				echo "${FUNCNAME}: skipping unrecognized file format: ${file}"
				;;
		esac
	done
	find . -mindepth 1 -maxdepth 1 ! -type l -print0 | \
		${XARGS} -0 chmod -fR a+rX,u+w,g-w,o-w
}

:
