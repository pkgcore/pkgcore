#!/usr/bin/python
import sys
sys.path.insert(0,__file__)
import profile
profile.run("import build_installed_state_graph", "stats.pdb")
