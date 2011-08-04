# Copyright: 2011 Brian Harring <ferringb@gmail.com>
# License: GPL2/BSD 3 clause

from pkgcore.util import commandline
from snakeoil.demandload import demandload
demandload(globals(),
    "pkgcore.ebuild:profiles",
)

commands = []
# parent
# use
# eapi
# deprecated
# defaults
# provided
# changelog, once a changelog parser is available
# desc: possibly
# info: desc, keywords known, known profiles (possibly putting it elsewhere)
# global known flags, etc

def mk_profile(value):
    return profiles.ProfileStack(commandline.existant_path(value))


class _base(commandline.ArgparseCommand):

    def bind_to_parser(self, parser):
        commandline.ArgparseCommand.bind_to_parser(self, parser)
        parser.add_argument("profile", help="path to the profile to inspect",
            type=mk_profile)

_register_command = commandline.register_command(commands)

class parent(_base):

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        out.write("\n".join(x.path for x in namespace.profile.stack))


class eapi(_base):

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        eapis = set(x.eapi_obj.magic for x in namespace.profile.stack)
        out.write("\n".join(sorted(eapis)))


class deprecated(_base):

    __metaclass__ = _register_command

    def __call__(self, namespace, out, err):
        deprecated = [x for x in namespace.profile.stack if x.deprecated]
        for idx, profile in enumerate(deprecated):
            if idx:
                out.write()
            out.write(out.bold, out.fg("cyan"), profile.path, out.reset, ":")
            data = profile.deprecated
            if data[0]:
                out.write(" ", out.fg("yellow"), "replacement profile", out.reset, ": %s" % (data[0],))
            if data[1]:
                out.write(" ", out.fg("yellow"), "deprecation message", out.reset, ":")
                for line in data[1].split("\n"):
                    out.write(line, prefix='  ')
        

_color_parent = commandline.mk_argparser(color=True, domain=False, add_help=False)

def bind_parser(parser, name):
    subparsers = parser.add_subparsers(help="%s commands" % (name,))
    for command in commands:
        subparser = subparsers.add_parser(command.__name__.lower(),
            help=command.__doc__, parents=[_color_parent])
        command().bind_to_parser(subparser)
