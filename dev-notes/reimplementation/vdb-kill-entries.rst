======================
 killable vdb entries
======================

List of key entries we can ignore. Beyond that, the usual pkg
attributes need to survive, and/or be regenerated. Regeneration of
license/keywords should be external using saved env, not done on the
fly normally (imo).

- LDFLAGS
- CFLAGS
- CXXFLAGS
- ASFLAGS
- DEBUGBUILD
