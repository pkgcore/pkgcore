__all__ = ("skip_signatures",)

msg_header = "-----BEGIN PGP SIGNED MESSAGE-----\n"
msg_header_len = len(msg_header)
msg_hash = "Hash:"
msg_hash_len = len(msg_hash)
sig_header = "-----BEGIN PGP SIGNATURE-----\n"
sig_header_len = len(sig_header)
sig_footer = "-----END PGP SIGNATURE-----\n"
sig_footer_len = len(sig_footer)


def skip_signatures(iterable):
    i = iter(iterable)
    # format is-
    # """
    # -----BEGIN PGP SIGNED MESSAGE-----
    # Hash: SHA1
    #
    # """

    for line in i:
        if line.endswith(msg_header):
            # swallow the armor headers and the blank line ending them.
            for line in i:
                if not line.startswith(msg_hash):
                    break
            continue
        if line.endswith(sig_header):
            # swallow the signature through its footer.
            for line in i:
                if line.endswith(sig_footer):
                    break
            continue
        yield line
