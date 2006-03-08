# Copyright: 2005 Gentoo Foundation
# License: GPL2
# $Id:$

from twisted.trial import unittest
from portage import spawn
from portage.test.fs.test_util import TempDirMixin
import os

class SpawnTest(TempDirMixin, unittest.TestCase):
	
	def setUp(self):
		self.orig_env = os.environ["PATH"]
		TempDirMixin.setUp(self)
		os.environ["PATH"] = ":".join([self.dir] + self.orig_env.split(":"))
		self.null = os.open("/dev/null", os.O_WRONLY)

	def tearDown(self):
		os.close(self.null)
		os.environ["PATH"] = self.orig_env
		TempDirMixin.tearDown(self)
		
	def test_find_path(self):
		script_name = "portage-findpath-test.sh"
		self.assertRaises(spawn.CommandNotFound, spawn.find_binary, script_name)
		fp = os.path.join(self.dir, script_name)
		open(fp,"w")
		os.chmod(fp, 0644)
		self.assertRaises(spawn.CommandNotFound, spawn.find_binary, script_name)
		os.chmod(fp, 0755)
		self.failUnlessSubstring(self.dir, spawn.find_binary(script_name))
	
	def test_spawn_get_output(self):
		fp = os.path.join(self.dir, "portage-spawn-getoutput.sh")
		for r, s, text, args in [
			[0, ["dar\n"], "echo dar\n", {}],
			[0, ["dar"], "echo -n dar", {}],
			[1, ["blah\n","dar\n"], "echo blah\necho dar\nexit 1", {}],
			[0, [], "echo dar 1>&2", {"fd_pipes":{1:1,2:self.null}}]]:

			open(fp, "w").write(text)
			os.chmod(fp, 0775)
			self.assertEqual([r,s], spawn.spawn_get_output(fp, spawn_type=spawn.spawn_bash, **args))

	
