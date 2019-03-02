## Package manager query commands

has_version() { return $(__ebd_ipc_cmd ${FUNCNAME} "" "$@"); }
best_version() { __ebd_ipc_cmd ${FUNCNAME} "" "$@"; }

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
