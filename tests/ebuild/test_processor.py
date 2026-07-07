from pkgcore.ebuild.atom import atom
from pkgcore.ebuild.processor import EbuildProcessor


class TestEnvironmentDump:
    def test_multibyte_function_body(self, repo):
        # raw non-ASCII in a function body makes the receive_env byte count
        # exceed the char count; reading as text over-read past the payload
        # (https://bugs.gentoo.org/930852)
        data = 'src_prepare() {\n\techo "café résumé naïve größe" || die\n}\n'
        repo.create_ebuild("cat/pkg-1", data=data)
        repo.sync()
        pkg = max(repo.itermatch(atom("cat/pkg")))
        env = pkg.environment.text_fileobj().read()
        assert "café résumé naïve größe" in env


class TestGenerateEnvStr:
    def _gen(self, env):
        # _generate_env_str only needs _readonly_vars; avoid spawning a daemon.
        proc = EbuildProcessor.__new__(EbuildProcessor)
        proc._readonly_vars = frozenset()
        return proc._generate_env_str(env)

    def test_all_exported_without_marker(self):
        # absent PKGCORE_NONEXPORTED_VARS everything is exported on a single line
        out = self._gen({"P": "foo-1", "PATH": "/bin", "arr": ["x", "y"]})
        assert "\n" not in out
        assert out.startswith("export ")
        assert "P='foo-1'" in out
        assert 'arr=([0]="x" [1]="y")' in out

    def test_nonexported_split(self):
        out = self._gen(
            {
                "PKGCORE_NONEXPORTED_VARS": "P ARCH USE SLOT",
                "P": "foo-1",
                "ARCH": "amd64",
                "USE": "a b",
                "SLOT": "0",
                "PATH": "/bin",
                "HOME": "/tmp/h",
                "D": "/img/",
            }
        )
        plain_line, export_line = out.splitlines()
        assert not plain_line.startswith("export ")
        assert export_line.startswith("export ")
        # marked variables are bare assignments (unexported shell vars)
        for assign in ("ARCH=amd64", "P='foo-1'", "SLOT=0", "USE='a b'"):
            assert assign in plain_line
            assert assign not in export_line
        # everything else stays exported
        for assign in ("D='/img/'", "HOME='/tmp/h'", "PATH='/bin'"):
            assert assign in export_line
        # the marker itself never leaks
        assert "PKGCORE_NONEXPORTED_VARS" not in out

    def test_marker_only_nonexported(self):
        # when nothing is exported there is no export line
        out = self._gen({"PKGCORE_NONEXPORTED_VARS": "P", "P": "foo-1"})
        assert out == "P='foo-1'"
