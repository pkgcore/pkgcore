#!/usr/bin/python
import sys
sys.path.insert(0,__file__)
import profile
Profile.run("import build_installed_state_graph", "stats.pdb")
