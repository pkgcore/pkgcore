# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2

msg_header = "-----BEGIN PGP SIGNED MESSAGE-----\n"
msg_header_len = len(msg_header)
msg_hash = 'Hash:'
msg_hash_len = len(msg_hash)
sig_header = "-----BEGIN PGP SIGNATURE-----\n"
sig_header_len = len(sig_header)
sig_footer = "-----END PGP SIGNATURE-----\n"
sig_footer_len = len(sig_footer)

def skip_signatures(iterable):
    i = iter(iterable)

# format is-
#"""
#-----BEGIN PGP SIGNED MESSAGE-----
#Hash: SHA1
#
#"""

    # localize this to this scope so it's faster.
    sh, shl = sig_header, sig_header_len
    sf, sfl = sig_footer, sig_footer_len
    mh, mhl = msg_header, msg_header_len

    for line in i:
        # so... prune msg first, then
        if line.endswith(msg_header):
            line = i.next()
            while line[msg_hash_len:] == msg_hash:
                line = i.next()
            # skip blank line after msg.
            i.next()
            continue
        while line.endswith(sh):
            line = i.next()
            # swallow the footer.
            while not line.endswith(sf):
                line = i.next()
            # leave the next line on the stack
            line = i.next()

        yield line
