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
			local -a prefix=( $(echo ${args/*--prefix[= ]}) )
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


default_src_configure() { __phase_src_configure; }
