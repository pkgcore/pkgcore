import os
from types import SimpleNamespace

import pytest

from pkgcore.scripts import pclean
from pkgcore.test.scripts.helpers import ArgParseMixin


class TestCommandline(ArgParseMixin):
    _argparser = pclean.argparser

    suppress_domain = True

    def test_parser(self):
        self.assertError("the following arguments are required: subcommand")


@pytest.mark.parametrize(
    ("pretend", "tty", "removed", "output"),
    (
        (False, False, True, []),
        (True, False, False, ["{target}"]),
        (True, True, False, ["Would remove {target}"]),
    ),
)
def test_remove(tmp_path, monkeypatch, pretend, tty, removed, output):
    target = tmp_path / "distfile.tar.gz"
    target.write_text("")
    monkeypatch.setattr(pclean.sys.stdout, "isatty", lambda: tty)
    written = []
    out = SimpleNamespace(write=written.append)
    options = SimpleNamespace(
        remove=iter([(os.remove, str(target))]),
        pretend=pretend,
        verbosity=0,
        prog="pclean",
    )
    assert pclean._remove(options, out, out) == 0
    assert target.exists() is not removed
    assert written == [x.format(target=target) for x in output]
