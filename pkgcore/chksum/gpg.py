# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

sig_header = '-----BEGIN PGP SIGNATURE-----'
sig_header_len = len(sig_header)
sig_footer = '-----END PGP SIGNATURE-----'
sig_footer_len = len(sig_footer)

def skip_signatures(iterable):
    # localize this to this scope so it's faster.
    sh, shl = sig_header, sig_header_len
    sf, sfl = sig_footer, sig_footer_len
    i = iter(iterable)
    for line in i:
        if line[:shl] == sh:
            line = i.next()
            while line[:sfl] != sf:
                line = i.next()
            continue
        yield line
