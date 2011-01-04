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
    if has "${EBUILD_PHASE}" nofetch unpack prepare configure compile test; then
        if [ "${EBUILD_PHASE}" == 'nofetch' ]; then
            default_pkg_nofetch
        else
            default_src_${EBUILD_PHASE}
        fi
    else
        die "default is not available in ebuild phase '${EBUILD_PHASE}'"
    fi
}

inject_phase_funcs pkgcore_eapi2 src_{configure,prepare}
inject_common_phase_funcs

true
