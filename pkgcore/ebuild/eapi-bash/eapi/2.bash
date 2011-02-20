# Copyright 2011 Brian Harring <ferringb@gmail.com>
# license GPL2/BSD 3

pkgcore_eapi2_src_configure()
{
    has "${EAPI:0}" 0 1 && die "src_configure isn't available from EAPI's below 2"
    if [[ -x ${ECONF_SOURCE:-.}/configure ]] ; then
        econf
    fi
}

pkgcore_eapi2_src_prepare() {
    has "${EAPI:0}" 0 1 && die "src_prepare isn't available from EAPI's below 2"
    :
}

for x in pkg_nofetch src_{unpack,compile,test}; do
    eval "default_${x}() { pkgcore_common_${x}; }"
done
unset x

default_src_configure() { pkgcore_eapi2_src_configure; }
default_src_prepare()   { pkgcore_eapi2_src_prepare; }

default() {
	local default_type=$(type -t default_pkg_${EBUILD_PHASE})

	# note we do substitution instead of direct comparison to protect against
	# any bash misbehaviours across versions.
	if [[ ${default_type/function} == ${default_type} ]]; then
		default_type=$(type -t default_src_${EBUILD_PHASE})
		if [[ ${default_type/function} == ${default_type} ]]; then
			die "default is not available in ebuild phase '${EBUILD_PHASE}'"
		fi
		default_type=src
	else
		default_type=pkg
	fi
	default_${default_type}_${EBUILD_PHASE}
}

inject_phase_funcs pkgcore_eapi2 src_{configure,prepare}
inject_common_phase_funcs

true
