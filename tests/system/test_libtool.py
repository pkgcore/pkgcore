import io

from pkgcore.system import libtool


def rewrite(content):
    return libtool.rewrite_lafile(io.StringIO(content), "libfoo.la")


def parsed(content):
    return libtool.parse_lafile(io.StringIO(content))


def test_clean_file_is_left_alone():
    assert rewrite(
        "dependency_libs=' -L/usr/lib64 -lbar'\ninherited_linker_flags=' -pthread'\n"
    ) == (False, None)


def test_flags_move_into_inherited_linker_flags():
    updated, content = rewrite(
        "dependency_libs=' -lbar -pthread'\ninherited_linker_flags=''\n"
    )
    assert updated
    data = parsed(content)
    assert data["dependency_libs"] == " -lbar"
    assert data["inherited_linker_flags"] == " -pthread"
    assert "inherited_flags" not in data


def test_flags_stay_without_inherited_linker_flags():
    assert rewrite("dependency_libs=' -lbar -pthread'\n") == (False, None)
