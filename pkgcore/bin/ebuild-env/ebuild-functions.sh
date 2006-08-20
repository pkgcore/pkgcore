#!/bin/bash
# ebuild-functions.sh; ebuild env functions, saved with the ebuild (not specific to the portage version).
# Copyright 2004-2005 Gentoo Foundation

use()
{
	if useq ${1}; then
		return 0
	fi
	return 1
}

has()
{
	if hasq "$@"; then
		return 0
	fi
	return 1
}

use_with()
{
	if [ -z "$1" ]; then
		echo "!!! use_with() called without a parameter." >&2
		echo "!!! use_with <USEFLAG> [<flagname> [value]]" >&2
		return
	fi

	local UW_SUFFIX=""	
	if [ ! -z "${3}" ]; then
		UW_SUFFIX="=${3}"
	fi

	local UWORD="$2"
	if [ -z "${UWORD}" ]; then
		UWORD="$1"
	fi
	
	if useq $1; then
		echo "--with-${UWORD}${UW_SUFFIX}"
		return 0
	else
		echo "--without-${UWORD}"
		return 1
	fi
}

use_enable()
{
	if [ -z "$1" ]; then
		echo "!!! use_enable() called without a parameter." >&2
		echo "!!! use_enable <USEFLAG> [<flagname> [value]]" >&2
		return
	fi

	local UE_SUFFIX=""	
	if [ ! -z "${3}" ]; then
		UE_SUFFIX="=${3}"
	fi

	local UWORD="$2"
	if [ -z "${UWORD}" ]; then
		UWORD="$1"
	fi
	
	if useq $1; then
		echo "--enable-${UWORD}${UE_SUFFIX}"
		return 0
	else
		echo "--disable-${UWORD}"
		return 1
	fi
}

econf()
{
	local ret
	ECONF_SOURCE="${ECONF_SOURCE:-.}"
	if [ -x "${ECONF_SOURCE}/configure" ]; then
		if ! hasq autoconfig $RESTRICT; then
			if [ -e /usr/share/gnuconfig/ ]; then
				local x
				for x in $(find ${WORKDIR} -type f '(' -name config.guess -o -name config.sub ')' ); do
					echo " * econf: updating ${x/${WORKDIR}\/} with /usr/share/gnuconfig/${x##*/}"
					cp -f "/usr/share/gnuconfig/${x##*/}" "${x}"
					chmod a+x "${x}"
				done
			fi
		fi
		if [ ! -z "${CBUILD}" ]; then
			EXTRA_ECONF="--build=${CBUILD} ${EXTRA_ECONF}"
		fi

		# if the profile defines a location to install libs to aside from default, pass it on.
		# if the ebuild passes in --libdir, they're responsible for the conf_libdir fun.
		LIBDIR_VAR="LIBDIR_${ABI}"
		if [ -n "${ABI}" -a -n "${!LIBDIR_VAR}" ]; then
			CONF_LIBDIR="${!LIBDIR_VAR}"
		fi
		unset LIBDIR_VAR
		if [ -n "${CONF_LIBDIR}" ] && [ "${*/--libdir}" == "$*" ]; then
			if [ "${*/--exec-prefix}" != "$*" ]; then
				local args="$(echo $*)"
				local -a pref=($(echo ${args/*--exec-prefix[= ]}))
				CONF_PREFIX=${pref}
				[ "${CONF_PREFIX:0:1}" != "/" ] && CONF_PREFIX="/${CONF_PREFIX}"
			elif [ "${*/--prefix}" != "$*" ]; then
 				local args="$(echo $*)"
 				local -a pref=($(echo ${args/*--prefix[= ]}))
 				CONF_PREFIX=${pref}
				[ "${CONF_PREFIX:0:1}" != "/" ] && CONF_PREFIX="/${CONF_PREFIX}"
			else
				CONF_PREFIX="/usr"
 			fi
 			export CONF_PREFIX
			[ "${CONF_LIBDIR:0:1}" != "/" ] && CONF_LIBDIR="/${CONF_LIBDIR}"

			CONF_LIBDIR_RESULT="${CONF_PREFIX}${CONF_LIBDIR}"
			for X in 1 2 3; do
				# The escaping is weird. It will break if you escape the last one.
				CONF_LIBDIR_RESULT="${CONF_LIBDIR_RESULT//\/\///}"
			done

			EXTRA_ECONF="--libdir=${CONF_LIBDIR_RESULT} ${EXTRA_ECONF}"
		fi
		local EECONF_CACHE
		if request_confcache "${T}/local_cache"; then
			EECONF_CACHE="--cache-file=${T}/local_cache"
		fi
		echo ${ECONF_SOURCE}/configure \
			--prefix=/usr \
			--host=${CHOST} \
			--mandir=/usr/share/man \
			--infodir=/usr/share/info \
			--datadir=/usr/share \
			--sysconfdir=/etc \
			--localstatedir=/var/lib \
			${EXTRA_ECONF} \
			${EECONF_CACHE} \
			"$@"

		if ! ${ECONF_SOURCE}/configure \
			--prefix=/usr \
			--host=${CHOST} \
			--mandir=/usr/share/man \
			--infodir=/usr/share/info \
			--datadir=/usr/share \
			--sysconfdir=/etc \
			--localstatedir=/var/lib \
			${EXTRA_ECONF} \
			${EECONF_CACHE} \
			"$@" ; then

			if [ -s config.log ]; then
				echo
				echo "!!! Please attach the config.log to your bug report:"
				echo "!!! ${PWD}/config.log"
			fi
			die "econf failed"
		fi

		# store the returned exit code.  don't rely on update_confcache returning true.
		ret=$?
		update_confcache "${T}/local_cache"
		return $ret
	else
		die "no configure script found"
	fi
}

strip_duplicate_slashes ()
{
	if [ -n "${1}" ]; then
		local removed="${1/\/\///}"
		[ "${removed}" != "${removed/\/\///}" ] && removed=$(strip_duplicate_slashes "${removed}")
		echo ${removed}
	fi
}

einstall() 
{
	# CONF_PREFIX is only set if they didn't pass in libdir above
	LIBDIR_VAR="LIBDIR_${ABI}"
	if [ -n "${ABI}" -a -n "${!LIBDIR_VAR}" ]; then
		CONF_LIBDIR="${!LIBDIR_VAR}"
	fi
	unset LIBDIR_VAR
	if [ -n "${CONF_LIBDIR}" ] && [ "${CONF_PREFIX:-unset}" != "unset" ]; then
		EI_DESTLIBDIR="${D}/${CONF_PREFIX}/${CONF_LIBDIR}"
		EI_DESTLIBDIR="$(strip_duplicate_slashes ${EI_DESTLIBDIR})"
		EXTRA_EINSTALL="libdir=${EI_DESTLIBDIR} ${EXTRA_EINSTALL}"
		unset EI_DESTLIBDIR
	fi

	if [ -f ./[mM]akefile -o -f ./GNUmakefile ] ; then
		if [ ! -z "${PORTAGE_DEBUG}" ]; then
			make -n prefix=${D}/usr \
				datadir=${D}/usr/share \
				infodir=${D}/usr/share/info \
		  		localstatedir=${D}/var/lib \
				mandir=${D}/usr/share/man \
				sysconfdir=${D}/etc \
				${EXTRA_EINSTALL} \
				"$@" install
		fi
		make prefix=${D}/usr \
			datadir=${D}/usr/share \
			infodir=${D}/usr/share/info \
			localstatedir=${D}/var/lib \
			mandir=${D}/usr/share/man \
			sysconfdir=${D}/etc \
			${EXTRA_EINSTALL} \
			"$@" install || die "einstall failed" 
	else
		die "no Makefile found"
	fi
}

pkg_setup()
{
	return 
}

pkg_nofetch()
{
	[ -z "${SRC_URI}" ] && return

	echo "!!! The following are listed in SRC_URI for ${PN}:"
	for MYFILE in `echo ${SRC_URI}`; do
		echo "!!!   $MYFILE"
	done
}

src_unpack()
{
	if [ "${A}" != "" ]; then
		unpack ${A}
	fi	
}

src_compile()
{
	if [ -x ./configure ]; then
		econf || die "econf failed"
	fi
	if [ -f Makefile ] || [ -f GNUmakefile ] || [ -f makefile ]; then
		emake || die "emake failed"
	fi
}

src_test() 
{ 
	addpredict /
	if make check -n &> /dev/null; then
		echo ">>> Test phase [check]: ${CATEGORY}/${PF}"
		if ! make check; then
			hasq test $FEATURES && die "Make check failed. See above for details."
			hasq test $FEATURES || eerror "Make check failed. See above for details."
		fi
	elif make test -n &> /dev/null; then
		echo ">>> Test phase [test]: ${CATEGORY}/${PF}"
		if ! make test; then
			hasq test $FEATURES && die "Make test failed. See above for details."
			hasq test $FEATURES || eerror "Make test failed. See above for details."
		fi
  else
		echo ">>> Test phase [none]: ${CATEGORY}/${PF}"
	fi
	SANDBOX_PREDICT="${SANDBOX_PREDICT%:/}"
}

src_install() 
{ 
	return 
}

pkg_preinst()
{
	return
}

pkg_postinst()
{
	return
}

pkg_prerm()
{
	return
}

pkg_postrm()
{
	return
}

into()
{
	if [ $1 == "/" ]; then
		export DESTTREE=""
	else
		export DESTTREE=$1
		if [ ! -d "${D}${DESTTREE}" ]; then
			install -d "${D}${DESTTREE}"
		fi
	fi
}

insinto()
{
	if [ "$1" == "/" ]; then
		export INSDESTTREE=""
	else
		export INSDESTTREE=$1
		if [ ! -d "${D}${INSDESTTREE}" ]; then
			install -d "${D}${INSDESTTREE}"
		fi
	fi
}

exeinto()
{
	if [ "$1" == "/" ]; then
		export EXEDESTTREE=""
	else
		export EXEDESTTREE="$1"
		if [ ! -d "${D}${EXEDESTTREE}" ]; then
			install -d "${D}${EXEDESTTREE}"
		fi
	fi
}

docinto()
{
	if [ "$1" == "/" ]; then
		export DOCDESTTREE=""
	else
		export DOCDESTTREE="$1"
		if [ ! -d "${D}usr/share/doc/${PF}/${DOCDESTTREE}" ]; then
			install -d "${D}usr/share/doc/${PF}/${DOCDESTTREE}"
		fi
	fi
}

true
