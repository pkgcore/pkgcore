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

class parent(_base):

    __metaclass__ = commandline.register_command(commands)

    def __call__(self, namespace, out, err):
        out.write("\n".join(x.path for x in namespace.profile.stack))
        return 0

def bind_parser(parser, name):
    subparsers = parser.add_subparsers(help="%s commands" % (name,))
    for command in commands:
        subparser = subparsers.add_parser(command.__name__.lower(),
            help=command.__doc__)
        command().bind_to_parser(subparser)
