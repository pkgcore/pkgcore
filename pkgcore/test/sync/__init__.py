# Copyright: 2006 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

def make_bogus_syncer(raw_kls):
    class bogus_syncer(raw_kls):
        binary = "/tmp/crack-monkeys-rule-if-you-have-this-binary-you-are-insane"
    return bogus_syncer

def make_valid_syncer(raw_kls):
    class valid_syncer(raw_kls):
        binary = "/bin/sh"
    return valid_syncer
