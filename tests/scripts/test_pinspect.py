from pkgcore.ebuild import atom
from pkgcore.scripts import pinspect
from pkgcore.test.scripts.helpers import ArgParseMixin


class TestQuery(ArgParseMixin):
    _argparser = pinspect.argparser
    suppress_domain = True

    def test_multiple_atoms(self):
        options = self.parse(
            "query", "mass_best_version", "--eapi", "8", "cat/pkg", "cat/other:1"
        )
        assert options.atom == [atom.atom("cat/pkg"), atom.atom("cat/other:1")]
