# Copyright: 2006-2009 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD

import os
import signal

from snakeoil import process
from snakeoil.test.mixins import TempDirMixin

from pkgcore import spawn
from pkgcore.test import TestCase, SkipTest


def capability_based(capable, msg):
    def internal_f(f):
        if not capable():
            f.skip = msg
        return f
    return internal_f


class SpawnTest(TempDirMixin, TestCase):

    def __init__(self, *a, **kw):
        try:
            self.bash_path = process.find_binary("bash")
            self.null_file = open("/dev/null", "w")
            self.null = self.null_file.fileno()
        except process.CommandNotFound:
            self.skip = "bash wasn't found.  this will be ugly."
        super(SpawnTest, self).__init__(*a, **kw)

    def setUp(self):
        self.orig_env = os.environ["PATH"]
        TempDirMixin.setUp(self)
        os.environ["PATH"] = ":".join([self.dir] + self.orig_env.split(":"))

    def tearDown(self):
        self.null_file.close()
        os.environ["PATH"] = self.orig_env
        TempDirMixin.tearDown(self)

    def generate_script(self, filename, text):
        if not os.path.isabs(filename):
            fp = os.path.join(self.dir, filename)
        with open(fp, "w") as f:
            f.write("#!/usr/bin/env bash\n")
            f.write(text)
        os.chmod(fp, 0750)
        self.assertEqual(os.stat(fp).st_mode & 0750, 0750)
        return fp

    def test_get_output(self):
        filename = "pkgcore-spawn-getoutput.sh"
        for r, s, text, args in (
                [0, ["dar\n"], "echo dar\n", {}],
                [0, ["dar"], "echo -n dar", {}],
                [1, ["blah\n", "dar\n"], "echo blah\necho dar\nexit 1", {}],
                [0, [], "echo dar 1>&2", {"fd_pipes": {1: 1, 2: self.null}}]):

            fp = self.generate_script(filename, text)
            self.assertEqual(
                [r, s],
                spawn.spawn_get_output(fp, spawn_type=spawn.spawn_bash, **args))

        os.unlink(fp)

    @capability_based(spawn.is_sandbox_capable, "sandbox binary wasn't found")
    def test_sandbox(self):
        if os.environ.get('SANDBOX_ON', False):
            raise SkipTest("sandbox doesn't like running inside itself")
        fp = self.generate_script(
            "pkgcore-spawn-sandbox.sh", "echo $LD_PRELOAD")
        ret = spawn.spawn_get_output(fp, spawn_type=spawn.spawn_sandbox)
        self.assertTrue(
            ret[1], msg="no output; exit code was %s; script "
            "location %s" % (ret[0], fp))
        self.assertIn(
            "libsandbox.so",
            [os.path.basename(x.strip()) for x in ret[1][0].split()])
        os.unlink(fp)

    @capability_based(spawn.is_sandbox_capable, "sandbox binary wasn't found")
    def test_sandbox_empty_dir(self):
        """sandbox gets pissy if it's ran from a nonexistent dir

        this verifies our fix works.
        """
        if os.environ.get('SANDBOX_ON', False):
            raise SkipTest("sandbox doesn't like running inside itself")
        fp = self.generate_script(
            "pkgcore-spawn-sandbox.sh", "echo $LD_PRELOAD")
        dpath = os.path.join(self.dir, "dar")
        os.mkdir(dpath)
        try:
            cwd = os.getcwd()
        except OSError:
            cwd = None
        try:
            os.chdir(dpath)
            os.rmdir(dpath)
            self.assertIn(
                "libsandbox.so",
                [os.path.basename(x.strip()) for x in spawn.spawn_get_output(
                    fp, spawn_type=spawn.spawn_sandbox, cwd='/')[1][0].split()])
            os.unlink(fp)
        finally:
            if cwd is not None:
                os.chdir(cwd)

    def test_process_exit_code(self):
        self.assertEqual(0, spawn.process_exit_code(0), "exit code failed")
        self.assertEqual(
            16, spawn.process_exit_code(16 << 8), "signal exit code failed")

    def generate_background_pid(self):
        try:
            return spawn.spawn(["sleep", "60s"], returnpid=True)[0]
        except process.CommandNotFound:
            raise SkipTest(
                "can't complete the test, sleep binary doesn't exist")

    def test_spawn_returnpid(self):
        pid = self.generate_background_pid()
        try:
            self.assertEqual(
                None, os.kill(pid, 0),
                "returned pid was invalid, or sleep died")
            self.assertEqual(
                True, pid in spawn.spawned_pids,
                "pid wasn't recorded in global pids")
        finally:
            os.kill(pid, signal.SIGKILL)

    def test_cleanup_pids(self):
        pid = self.generate_background_pid()
        spawn.cleanup_pids([pid])
        self.assertRaises(OSError, os.kill, pid, 0)
        self.assertNotIn(
            pid, spawn.spawned_pids, "pid wasn't removed from global pids")

    def test_bash(self):
        # bash builtin for true without exec'ing true (eg, no path lookup)
        self.assertEqual(0, spawn.spawn_bash(":"))

    def test_umask(self):
        fp = self.generate_script(
            "pkgcore-spawn-umask.sh", "#!%s\numask" % self.bash_path)
        try:
            old_umask = os.umask(0)
            if old_umask == 0:
                # crap.
                desired = 022
                os.umask(desired)
            else:
                desired = 0
            self.assertEqual(
                str(desired).lstrip("0"),
                spawn.spawn_get_output(fp)[1][0].strip().lstrip("0"))
        finally:
            os.umask(old_umask)
