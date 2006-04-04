#!/usr/bin/python
import sys
sys.path.insert(0,__file__)
import profile
import build_installed_state_graph
profile.run("g=build_installed_state_graph.gen_graph();g.blocking_atoms()", "stats.pdb")
