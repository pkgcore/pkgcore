import textwrap
from io import StringIO

import pytest

from pkgcore.config import central, cparser, errors


def test_case_sensitive_config_parser():
    cp = cparser.CaseSensitiveConfigParser()
    config = StringIO("[header]\nfoo=bar\nFOO=BAR\n[HEADER]\nfoo=notbar")
    cp.read_file(config)
    assert cp.get("header", "foo") == "bar"
    assert cp.get("header", "FOO") == "BAR"
    assert cp.get("HEADER", "foo") == "notbar"


class TestConfigFromIni:
    def test_config_from_ini(self):
        config = cparser.config_from_file(
            StringIO(
                textwrap.dedent(
                    """\
            [test]
            string = 'hi I am a string'
            list = foo bar baz
            true = yes
            false = no
        """
                )
            )
        )
        assert list(config.keys()) == ["test"]
        section = config["test"]
        for key, arg_type, value in (
            ("string", "str", "hi I am a string"),
            (
                "list",
                "list",
                ["foo", "bar", "baz"],
            ),
            ("true", "bool", True),
            ("false", "bool", False),
        ):
            assert section.render_value(None, key, arg_type) == value

    def test_missing_section_ref(self):
        config = cparser.config_from_file(
            StringIO(
                textwrap.dedent(
                    """\
            [test]
            ref = 'missing'
        """
                )
            )
        )
        section = config["test"]
        with pytest.raises(errors.ConfigurationError):
            section.render_value(
                central.ConfigManager([]), "ref", "ref:drawer"
            ).collapse()


@pytest.mark.parametrize(
    "value", ("https://example.org/%7Euser", "%(missing)s"), ids=("stray", "missing")
)
def test_bad_interpolation_is_a_parsing_error(value):
    with pytest.raises(errors.ParsingError):
        cparser.config_from_file(StringIO(f"[test]\nvalue = {value}\n"))


def test_interpolation():
    config = cparser.config_from_file(
        StringIO("[test]\nbase = /srv\nvalue = %(base)s/repo 100%%\n")
    )
    assert config["test"].render_value(None, "value", "str") == "/srv/repo 100%"
