from snakeoil.test import code_quality


class TestSlots(code_quality.Slots):
    namespaces = ("pkgcore",)
    # pkgcore has plenty of classes still lacking slots, so test_slots_mandatory
    # stays non-strict; shadowing is clean and stays that way.
    strict = ("test_shadowing",)
